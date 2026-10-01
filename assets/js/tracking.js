/*!
 * VIP PHONE — tracking + attribution (dùng chung cho mọi trang)
 *
 * Nạp TRƯỚC mọi script khác để `window.dataLayer` luôn tồn tại.
 * Không chứa PII. Không gửi dữ liệu đi đâu — chỉ đẩy vào dataLayer
 * để GTM/GA4 (nối ở gate sau) đọc.
 */
"use strict";

(function () {
  window.dataLayer = window.dataLayer || [];

  /** Khoá sessionStorage giữ attribution của lượt truy cập hiện tại. */
  var ATTRIBUTION_KEY = "vipphone_attribution_v1";

  /**
   * Whitelist tham số được phép ghi nhận.
   * KHÔNG bao giờ đọc/ghi tham số ngoài danh sách này — tránh PII lọt vào query string.
   */
  var TRACKED_PARAMS = [
    "src",
    "ref",
    "campaign",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content"
  ];

  var MAX_VALUE_LENGTH = 64;
  /**
   * Chỉ nhận ký tự an toàn. Giá trị lạ (khoảng trắng, dấu <, dấu nháy…)
   * bị loại bỏ chứ không được lưu thô.
   */
  var SAFE_VALUE = /^[A-Za-z0-9._~-]+$/;

  function sanitize(value) {
    if (value === null || value === undefined) return "";
    var v = String(value).trim().slice(0, MAX_VALUE_LENGTH);
    return SAFE_VALUE.test(v) ? v : "";
  }

  function readStored() {
    try {
      var raw = sessionStorage.getItem(ATTRIBUTION_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (err) {
      return {};
    }
  }

  function writeStored(data) {
    try {
      sessionStorage.setItem(ATTRIBUTION_KEY, JSON.stringify(data));
    } catch (err) {
      /* Chế độ riêng tư có thể chặn sessionStorage — không được làm hỏng trang. */
    }
  }

  /**
   * Đọc attribution một lần cho cả phiên.
   *
   * Quy tắc: tham số có trên URL sẽ GHI ĐÈ giá trị đã lưu (last-touch).
   * Tham số không có trên URL giữ nguyên giá trị đã lưu, nên điều hướng
   * nội bộ (index → success → redeem) không làm mất nguồn.
   */
  function captureAttribution() {
    var stored = readStored();
    var params = new URLSearchParams(window.location.search);
    var changed = false;

    for (var i = 0; i < TRACKED_PARAMS.length; i++) {
      var key = TRACKED_PARAMS[i];
      if (!params.has(key)) continue;
      var value = sanitize(params.get(key));
      if (value && stored[key] !== value) {
        stored[key] = value;
        changed = true;
      }
    }

    if (changed) writeStored(stored);
    return stored;
  }

  function getAttribution() {
    return readStored();
  }

  /** Đẩy một event vào dataLayer. Không ném lỗi nếu có sự cố. */
  function track(event, extra) {
    try {
      var payload = { event: event };
      if (extra) {
        for (var key in extra) {
          if (Object.prototype.hasOwnProperty.call(extra, key)) payload[key] = extra[key];
        }
      }
      window.dataLayer.push(payload);
    } catch (err) {
      /* Tracking không bao giờ được làm hỏng luồng nghiệp vụ. */
    }
  }

  window.VPTrack = {
    captureAttribution: captureAttribution,
    getAttribution: getAttribution,
    track: track,
    TRACKED_PARAMS: TRACKED_PARAMS
  };

  captureAttribution();

  // `vipphone_landing_view` phát ra dựa trên thuộc tính `data-vp-page` của
  // <body>, KHÔNG bằng <script> nội tuyến. Lý do: CSP nghiêm `script-src 'self'`
  // chặn mọi script nội tuyến — xem app/security.py.
  var pageName = document.body && document.body.getAttribute("data-vp-page");
  if (pageName === "landing") {
    track("vipphone_landing_view");
  }
})();
