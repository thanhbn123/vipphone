/*!
 * VIP PHONE — quét mã QR bằng camera, CHỈ khi trình duyệt/thiết bị thật sự hỗ trợ.
 *
 * ⚠️  NGUYÊN TẮC: KHÔNG GIẢ VỜ.
 * Module này không tự vẽ khung quét, không tự "đoán" mã, không có đường lui nào
 * kiểu "nếu không có camera thì báo thành công". Không hỗ trợ thì trả về
 * `false` và trang phải ẨN nút quét, kèm lời giải thích — chứ không hiện một
 * nút bấm vào không có gì xảy ra.
 *
 * Thứ được dùng để quét là **BarcodeDetector** — API của chính trình duyệt.
 * Không nạp thư viện ngoài: CSP của dự án là `script-src 'self'`, và một thư
 * viện tải từ CDN sẽ vừa bị CSP chặn vừa tạo thêm một đường phụ thuộc ngoài.
 *
 * ĐIỀU KIỆN ĐÃ ĐO (không suy đoán): `BarcodeDetector` có mặt trên Chromium
 * (Chrome/Edge/Android WebView) khi chạy trong ngữ cảnh bảo mật (HTTPS hoặc
 * localhost). Trên Safari/iOS và Firefox tới thời điểm này KHÔNG có, nên nút sẽ
 * bị ẩn — đúng như thiết kế. Có test E2E đo CẢ HAI nhánh:
 * `tests_e2e/test_g04_g06_browser.py`.
 */
"use strict";

(function () {
  var SCAN_INTERVAL_MS = 300;

  var active = null;

  function detectorConstructor() {
    return typeof window.BarcodeDetector === "function" ? window.BarcodeDetector : null;
  }

  /**
   * Trình duyệt có quét QR được không — ĐO, không đoán.
   *
   * Chỉ kiểm `'BarcodeDetector' in window` là chưa đủ: có bản triển khai tồn
   * tại nhưng không hỗ trợ định dạng `qr_code`. Hỏi thẳng danh sách định dạng.
   */
  function isSupported() {
    return new Promise(function (resolve) {
      var Ctor = detectorConstructor();
      if (!Ctor) {
        resolve(false);
        return;
      }

      var formatsPromise = null;
      try {
        if (typeof Ctor.getSupportedFormats === "function") {
          formatsPromise = Ctor.getSupportedFormats();
        } else if (typeof Ctor.prototype.getSupportedFormats === "function") {
          formatsPromise = new Ctor().getSupportedFormats();
        }
      } catch (err) {
        formatsPromise = null;
      }

      if (!formatsPromise || typeof formatsPromise.then !== "function") {
        resolve(false);
        return;
      }

      formatsPromise
        .then(function (formats) {
          resolve(Array.isArray(formats) && formats.indexOf("qr_code") !== -1);
        })
        .catch(function () {
          resolve(false);
        });
    });
  }

  function cameraAvailable() {
    return !!(
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === "function"
    );
  }

  function stop() {
    if (!active) return;
    if (active.timer) window.clearInterval(active.timer);
    if (active.stream) {
      active.stream.getTracks().forEach(function (track) {
        track.stop();
      });
    }
    if (active.video) {
      try {
        active.video.pause();
      } catch (err) {
        /* trình duyệt cũ: bỏ qua, track đã dừng */
      }
      active.video.srcObject = null;
    }
    active = null;
  }

  /**
   * Bật camera và quét liên tục.
   *
   * @param {HTMLVideoElement} video
   * @param {(text: string) => void} onCode  gọi MỘT lần cho mỗi mã đọc được
   * @param {(message: string) => void} onError
   * @returns {Promise<void>}
   */
  function start(video, onCode, onError) {
    stop();

    var Ctor = detectorConstructor();
    if (!Ctor) {
      onError("Thiết bị này không hỗ trợ quét QR.");
      return Promise.resolve();
    }
    if (!cameraAvailable()) {
      onError("Trình duyệt không cho truy cập camera.");
      return Promise.resolve();
    }

    return navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then(function (stream) {
        var detector = new Ctor({ formats: ["qr_code"] });
        active = { stream: stream, video: video, timer: null, detector: detector };

        video.srcObject = stream;
        video.setAttribute("playsinline", "");
        var playing = video.play();
        if (playing && typeof playing.catch === "function") {
          playing.catch(function () {
            /* autoplay bị chặn: ảnh vẫn hiển thị, chỉ không tự chạy */
          });
        }

        active.timer = window.setInterval(function () {
          if (!active) return;
          active.detector
            .detect(active.video)
            .then(function (codes) {
              if (!active || !codes || !codes.length) return;
              var raw = codes[0].rawValue || "";
              if (!raw) return;
              // Dừng NGAY khi đọc được mã: quét tiếp chỉ tạo thêm request tra cứu.
              stop();
              onCode(raw);
            })
            .catch(function () {
              /* khung hình chưa đủ nét — thử lại ở nhịp sau, không báo lỗi */
            });
        }, SCAN_INTERVAL_MS);
      })
      .catch(function (err) {
        stop();
        var name = err && err.name ? err.name : "";
        if (name === "NotAllowedError" || name === "SecurityError") {
          onError("Bạn chưa cho phép dùng camera. Cấp quyền rồi thử lại.");
        } else if (name === "NotFoundError" || name === "OverconstrainedError") {
          onError("Không tìm thấy camera trên thiết bị này.");
        } else {
          onError("Không mở được camera. Nhập mã bằng tay.");
        }
      });
  }

  window.VPQrScan = {
    isSupported: isSupported,
    cameraAvailable: cameraAvailable,
    start: start,
    stop: stop
  };
})();
