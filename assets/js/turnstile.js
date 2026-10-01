/*!
 * VIP PHONE — Turnstile (chống spam) phía trình duyệt.
 *
 * VÌ SAO CÓ FILE NÀY: backend đã có adapter xác minh token ở server, nhưng trước
 * đây frontend KHÔNG có widget. Hệ quả: bật `TURNSTILE_REQUIRED=true` ở server thì
 * không có token nào được gửi lên ⇒ MỌI lead bị chặn 403. Nghĩa là tính năng
 * "bật được qua biến môi trường" trên thực tế KHÔNG bật được.
 *
 * File này nối đúng chỗ đó:
 *   1. hỏi `/api/public-config` xem Turnstile có BẬT không (và lấy khoá site),
 *   2. nếu bật: nạp script Cloudflare rồi render widget,
 *   3. cung cấp token cho `app.js` gắn vào payload.
 *
 * KHÔNG chứa secret. Khoá site là khoá CÔNG KHAI theo thiết kế Cloudflare.
 * CSP chỉ cho phép origin Cloudflare khi Turnstile BẬT (xem app/security.py).
 */
"use strict";

(function () {
  var SCRIPT_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
  var TIMEOUT_MS = 15000;

  var state = {
    enabled: false,
    siteKey: null,
    token: null,
    widgetId: null,
    ready: false,
    failed: false,
    warning: null
  };

  function apiBase() {
    var config = window.VIPPHONE_CONFIG || {};
    return config.apiBase || "";
  }

  function log() {
    if (window.console && console.warn) {
      console.warn.apply(console, ["[VIP PHONE turnstile]"].concat(
        Array.prototype.slice.call(arguments)
      ));
    }
  }

  function loadScript() {
    return new Promise(function (resolve, reject) {
      // Đã có sẵn (nạp lại trang, hoặc nhiều lần gọi) thì dùng luôn.
      if (window.turnstile) return resolve();
      var existing = document.querySelector('script[data-vp-turnstile]');
      if (existing) {
        existing.addEventListener("load", function () { resolve(); });
        existing.addEventListener("error", function () {
          reject(new Error("không nạp được script Cloudflare"));
        });
        return;
      }
      var script = document.createElement("script");
      script.src = SCRIPT_URL;
      script.async = true;
      script.defer = true;
      script.setAttribute("data-vp-turnstile", "1");
      script.addEventListener("load", function () { resolve(); });
      script.addEventListener("error", function () {
        reject(new Error("không nạp được script Cloudflare"));
      });
      document.head.appendChild(script);
    });
  }

  function fetchConfig() {
    return fetch(apiBase() + "/api/public-config", { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (body) {
        return (body && body.turnstile) || { enabled: false };
      });
  }

  /**
   * Chuẩn bị Turnstile. An toàn khi tắt: trả về ngay, không nạp gì từ Internet.
   *
   * `container` là phần tử để render widget. Nếu Turnstile TẮT, container được
   * để trống và ẩn — KHÔNG hiện khung rỗng làm khách tưởng hỏng.
   */
  function init(container) {
    return fetchConfig()
      .then(function (config) {
        state.enabled = config.enabled === true;
        state.siteKey = config.site_key || null;
        state.warning = config.warning || null;

        if (state.warning) {
          // Nói ra khi cấu hình nửa vời. Nuốt cảnh báo này là để người vận hành
          // tự đoán vì sao form hỏng.
          log(state.warning);
        }

        if (!state.enabled) {
          if (container) container.hidden = true;
          state.ready = true;
          return state;
        }

        if (container) {
          container.hidden = false;
        }

        return loadScript()
          .then(function () {
            return new Promise(function (resolve) {
              var done = false;
              var timer = window.setTimeout(function () {
                if (done) return;
                done = true;
                state.failed = true;
                log("hết thời gian chờ widget Turnstile");
                resolve(state);
              }, TIMEOUT_MS);

              try {
                state.widgetId = window.turnstile.render(container, {
                  sitekey: state.siteKey,
                  callback: function (token) {
                    state.token = token;
                  },
                  "error-callback": function () {
                    state.failed = true;
                    state.token = null;
                    return true;
                  },
                  "expired-callback": function () {
                    state.token = null;
                  }
                });
                window.clearTimeout(timer);
                done = true;
                state.ready = true;
                resolve(state);
              } catch (err) {
                window.clearTimeout(timer);
                done = true;
                state.failed = true;
                log("không render được widget:", err && err.message);
                resolve(state);
              }
            });
          })
          .catch(function (err) {
            // Không nạp được script (mạng chặn, CSP, Cloudflare sập).
            // KHÔNG im lặng: đánh dấu để UI nói ra, và để `app.js` biết mà xử lý.
            state.failed = true;
            state.ready = true;
            log("nạp Turnstile thất bại:", err && err.message);
            return state;
          });
      })
      .catch(function (err) {
        state.ready = true;
        state.failed = true;
        log("không đọc được /api/public-config:", err && err.message);
        return state;
      });
  }

  function getToken() {
    return state.token || null;
  }

  function isEnabled() {
    return state.enabled === true;
  }

  function hasFailed() {
    return state.failed === true;
  }

  /** Gọi sau khi gửi thành công để token cũ không dùng lại được. */
  function reset() {
    state.token = null;
    if (state.enabled && window.turnstile && state.widgetId !== null) {
      try {
        window.turnstile.reset(state.widgetId);
      } catch (err) {
        /* widget đã biến mất — không sao */
      }
    }
  }

  window.VPTurnstile = {
    init: init,
    getToken: getToken,
    isEnabled: isEnabled,
    hasFailed: hasFailed,
    reset: reset,
    state: state
  };
})();
