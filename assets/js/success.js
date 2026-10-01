/*!
 * VIP PHONE — trang thành công: hiển thị gift code và liên kết nhận quà
 *
 * ⚠️  BẢN DEMO CLIENT-ONLY — đọc `localStorage` của chính trình duyệt này.
 * Trang này KHÔNG xác nhận rằng lead đã được lưu ở đâu đó ngoài máy khách.
 */
"use strict";

(function () {
  var LEADS_KEY = "vipphone_leads_v1";
  var LAST_GIFT_KEY = "vipphone_last_gift_code";

  var util = window.VPUtil;
  var track = window.VPTrack.track;

  var detailsBox = document.getElementById("giftDetails");
  var codeBox = document.getElementById("giftCode");
  var qrBox = document.getElementById("qr");

  function readLeads() {
    try {
      var raw = localStorage.getItem(LEADS_KEY);
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }

  function readLastGiftCode() {
    try {
      return localStorage.getItem(LAST_GIFT_KEY);
    } catch (err) {
      return null;
    }
  }

  function buildRedeemUrl(giftCode) {
    var url = new URL("redeem.html", window.location.href);
    url.searchParams.set("code", giftCode);
    return url.toString();
  }

  function renderMissing() {
    codeBox.textContent = "---";
    detailsBox.textContent = "";
    var p = document.createElement("p");
    p.className = "status warn";
    p.textContent =
      "Không tìm thấy thông tin đăng ký trên trình duyệt này. Nếu bạn vừa đăng ký ở thiết bị khác, vui lòng đăng ký lại hoặc liên hệ VIP PHONE.";
    detailsBox.appendChild(p);
    if (qrBox) {
      qrBox.textContent = "";
      qrBox.hidden = true;
    }
  }

  function renderLead(lead) {
    codeBox.textContent = lead.gift_code;

    detailsBox.innerHTML = [
      '<strong class="gift-name">' + util.escapeHtml(lead.full_name) + "</strong>",
      '<span class="gift-meta">',
      util.escapeHtml(lead.iphone_model) + " · " + util.escapeHtml(lead.case_color),
      "</span>",
      '<span class="gift-meta">Số điện thoại: ' +
        util.escapeHtml(util.formatPhone(lead.phone)) +
        "</span>"
    ].join("");

    var redeemUrl = buildRedeemUrl(lead.gift_code);
    window.VPQr.renderQrUnavailable(qrBox, redeemUrl);

    track("vipphone_gift_code_viewed", { gift_code: lead.gift_code });
  }

  function init() {
    var giftCode = readLastGiftCode();

    if (!giftCode || !util.isWellFormedGiftCode(giftCode)) {
      renderMissing();
      return;
    }

    var normalized = util.normalizeGiftCode(giftCode);
    var lead = readLeads().find(function (item) {
      return util.normalizeGiftCode(item.gift_code) === normalized;
    });

    if (!lead) {
      renderMissing();
      return;
    }

    renderLead(lead);
  }

  init();
})();
