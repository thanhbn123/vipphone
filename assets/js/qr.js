/*!
 * VIP PHONE — render QR chuẩn lấy từ server.
 *
 * QR được sinh ở SERVER bằng thư viện `qrcode` (chuẩn ISO/IEC 18004) và phục
 * vụ tại `GET /api/gifts/{gift_code}/qr.png`.
 *
 * Nội dung QR CHỈ gồm URL công khai dạng `<PUBLIC_BASE_URL>/redeem?code=...`.
 * KHÔNG chứa tên, số điện thoại, công ty hay bất kỳ PII nào. Điều này được
 * kiểm bằng test giải mã QR thật (`tests/test_gifts_api.py`).
 *
 * Lịch sử: bản baseline cũ (`qr-lite.js`) VẼ một hình trông giống mã QR nhưng
 * không theo chuẩn nào và không đầu đọc nào quét được. File đó đã bị gỡ.
 */
"use strict";

(function () {
  var QR_STATE = "SERVER_QR_STANDARD";

  function apiBase() {
    var config = window.VIPPHONE_CONFIG || {};
    return config.apiBase || "";
  }

  function qrImageUrl(giftCode) {
    return apiBase() + "/api/gifts/" + encodeURIComponent(giftCode) + "/qr.png";
  }

  function redeemUrl(giftCode) {
    var url = new URL("redeem.html", window.location.href);
    url.searchParams.set("code", giftCode);
    return url.toString();
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

  function renderFallback(container, fallbackUrl) {
    container.innerHTML = "";
    container.classList.add("qr-placeholder");

    var title = document.createElement("p");
    title.className = "qr-placeholder-title";
    title.textContent = "Chưa tải được mã QR";
    container.appendChild(title);

    var note = document.createElement("p");
    note.className = "qr-placeholder-note";
    note.textContent = "Vui lòng dùng liên kết bên dưới để nhận quà.";
    container.appendChild(note);

    var link = document.createElement("a");
    link.className = "qr-placeholder-link";
    link.href = fallbackUrl;
    link.textContent = fallbackUrl;
    container.appendChild(link);

    var copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "secondary-btn qr-placeholder-copy";
    copyBtn.textContent = "SAO CHÉP LIÊN KẾT";
    copyBtn.addEventListener("click", function () {
      copyText(fallbackUrl).then(function (ok) {
        copyBtn.textContent = ok ? "ĐÃ SAO CHÉP" : "KHÔNG SAO CHÉP ĐƯỢC";
        window.setTimeout(function () {
          copyBtn.textContent = "SAO CHÉP LIÊN KẾT";
        }, 2000);
      });
    });
    container.appendChild(copyBtn);
  }

  /**
   * Hiển thị QR chuẩn. Nếu ảnh không tải được (mất mạng, mã không tồn tại),
   * hiện URL dạng văn bản để nhân viên vẫn làm việc được — không im lặng.
   */
  function renderQr(container, giftCode) {
    if (!container) return;

    container.innerHTML = "";
    container.classList.remove("qr-placeholder");

    var fallbackUrl = redeemUrl(giftCode);

    var img = document.createElement("img");
    img.className = "qr-image";
    img.alt = "Mã QR nhận quà cho mã " + giftCode;
    img.width = 220;
    img.height = 220;
    img.src = qrImageUrl(giftCode);

    img.addEventListener("error", function () {
      renderFallback(container, fallbackUrl);
    });

    container.appendChild(img);
  }

  window.VPQr = {
    state: QR_STATE,
    renderQr: renderQr,
    qrImageUrl: qrImageUrl,
    redeemUrl: redeemUrl
  };
})();
