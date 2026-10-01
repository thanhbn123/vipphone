/*!
 * VIP PHONE — render QR
 *
 * ⚠️  NOT_PRODUCTION — CHƯA CÓ QR THẬT.
 *
 * Bản baseline trước đây (`qr-lite.js`) VẼ một hình trông giống mã QR nhưng
 * bit sinh từ FNV-1a hash + XOR-shift PRNG, KHÔNG theo chuẩn ISO/IEC 18004.
 * Không đầu đọc QR nào quét được hình đó. Một hình giả trông như thật là
 * cái bẫy: nhân viên có thể đưa điện thoại ra quét và thất bại ngay tại
 * quầy phát quà.
 *
 * Vì vậy file này CHỦ ĐỘNG KHÔNG VẼ HÌNH GIỐNG QR. Nó hiển thị:
 *   1. dòng chữ nói rõ QR chưa khả dụng,
 *   2. URL nhận quà dạng văn bản để nhân viên gõ tay / dán,
 *   3. nút sao chép URL.
 *
 * QR chuẩn (thư viện `qrcode`, ISO/IEC 18004, sinh ở server) được thêm ở G02.
 * Cho tới lúc đó: QR = NOT_PRODUCTION và phải giữ nguyên nhãn này.
 */
"use strict";

(function () {
  var QR_STATE = "NOT_IMPLEMENTED";

  function renderQrUnavailable(container, redeemUrl) {
    if (!container) return;

    container.innerHTML = "";
    container.classList.add("qr-placeholder");
    container.setAttribute("role", "group");
    container.setAttribute("aria-label", "Mã QR nhận quà chưa khả dụng");

    var title = document.createElement("p");
    title.className = "qr-placeholder-title";
    title.textContent = "Mã QR chưa khả dụng";
    container.appendChild(title);

    var note = document.createElement("p");
    note.className = "qr-placeholder-note";
    note.textContent =
      "Bản này chưa sinh mã QR chuẩn. Vui lòng dùng liên kết bên dưới.";
    container.appendChild(note);

    if (redeemUrl) {
      var link = document.createElement("a");
      link.className = "qr-placeholder-link";
      link.href = redeemUrl;
      link.textContent = redeemUrl;
      container.appendChild(link);

      var copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "secondary-btn qr-placeholder-copy";
      copyBtn.textContent = "SAO CHÉP LIÊN KẾT";
      copyBtn.addEventListener("click", function () {
        copyText(redeemUrl).then(function (ok) {
          copyBtn.textContent = ok ? "ĐÃ SAO CHÉP" : "KHÔNG SAO CHÉP ĐƯỢC";
          window.setTimeout(function () {
            copyBtn.textContent = "SAO CHÉP LIÊN KẾT";
          }, 2000);
        });
      });
      container.appendChild(copyBtn);
    }

    if (window.console && console.warn) {
      console.warn(
        "[VIP PHONE] QR = " + QR_STATE + " — hình QR giả đã bị gỡ để tránh gây nhầm lẫn."
      );
    }
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(
        function () { return true; },
        function () { return false; }
      );
    }
    return Promise.resolve(false);
  }

  window.VPQr = {
    state: QR_STATE,
    renderQrUnavailable: renderQrUnavailable
  };
})();
