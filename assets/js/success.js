/*!
 * VIP PHONE — trang thành công: hiển thị gift code và QR chuẩn.
 *
 * Kết quả lead được server trả về và giữ tạm trong `sessionStorage` để hiển
 * thị lại. KHÔNG lưu số điện thoại ở đây.
 *
 * Nguồn chân lý là server: mã QR được tải từ `/api/gifts/{code}/qr.png`.
 */
"use strict";

(function () {
  var RESULT_KEY = "vipphone_last_gift_v1";

  var util = window.VPUtil;
  var track = window.VPTrack.track;

  var detailsBox = document.getElementById("giftDetails");
  var codeBox = document.getElementById("giftCode");
  var qrBox = document.getElementById("qr");

  function readResult() {
    try {
      var raw = sessionStorage.getItem(RESULT_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (err) {
      return null;
    }
  }

  function renderMissing() {
    codeBox.textContent = "---";
    detailsBox.textContent = "";

    var p = document.createElement("p");
    p.className = "status warn";
    p.setAttribute("role", "status");
    p.textContent =
      "Không tìm thấy thông tin đăng ký trong phiên làm việc này. " +
      "Nếu bạn vừa đăng ký thành công, hãy liên hệ VIP PHONE để được hỗ trợ.";
    detailsBox.appendChild(p);

    if (qrBox) {
      qrBox.textContent = "";
      qrBox.hidden = true;
    }
  }

  function renderResult(result) {
    codeBox.textContent = result.gift_code;

    detailsBox.textContent = "";

    var name = document.createElement("strong");
    name.className = "gift-name";
    name.textContent = result.full_name || "";
    detailsBox.appendChild(name);

    var meta = document.createElement("span");
    meta.className = "gift-meta";
    meta.textContent = [result.iphone_model, result.case_color]
      .filter(Boolean)
      .join(" · ");
    detailsBox.appendChild(meta);

    if (result.duplicate === true) {
      var note = document.createElement("p");
      note.className = "status warn";
      note.setAttribute("role", "status");
      note.textContent =
        "Bạn đã đăng ký trước đó cho dòng máy này, nên hệ thống giữ nguyên mã quà cũ.";
      detailsBox.appendChild(note);
    }

    window.VPQr.renderQr(qrBox, result.gift_code);
    track("vipphone_gift_code_viewed", { gift_code: result.gift_code });
  }

  function init() {
    var result = readResult();

    if (!result || !result.gift_code || !util.isWellFormedGiftCode(result.gift_code)) {
      renderMissing();
      return;
    }

    renderResult(result);
  }

  init();
})();
