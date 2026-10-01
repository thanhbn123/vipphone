/*!
 * VIP PHONE — trang nhân viên: tra cứu gift code và xác nhận phát quà
 *
 * ⚠️  CHƯA CÓ XÁC THỰC NHÂN VIÊN — STAFF AUTH = OPEN.
 * Bất kỳ ai mở được trang này đều có thể tra cứu và xác nhận phát quà.
 * Trang chỉ được dùng cho DEMO/STAGING, KHÔNG được coi là secure production.
 * Xác thực nhân viên được thêm ở G04.
 *
 * ⚠️  Trạng thái cuối cùng được ghi vào `localStorage` của CHÍNH trình duyệt
 * này. Hai nhân viên trên hai máy có thể phát quà hai lần cho cùng một mã.
 * Từ G03, quyết định trạng thái chuyển về server (atomic, chống double-spend).
 */
"use strict";

(function () {
  var LEADS_KEY = "vipphone_leads_v1";

  var util = window.VPUtil;
  var track = window.VPTrack.track;

  var form = document.getElementById("redeemForm");
  var codeInput = document.getElementById("redeemCode");
  var result = document.getElementById("redeemResult");

  if (!form || !codeInput || !result) return;

  var currentLead = null;

  function loadLeads() {
    try {
      var raw = localStorage.getItem(LEADS_KEY);
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }

  function saveLeads(leads) {
    try {
      localStorage.setItem(LEADS_KEY, JSON.stringify(leads));
      return true;
    } catch (err) {
      return false;
    }
  }

  function findLeadIndex(leads, code) {
    var normalized = util.normalizeGiftCode(code);
    for (var i = 0; i < leads.length; i++) {
      if (util.normalizeGiftCode(leads[i].gift_code) === normalized) return i;
    }
    return -1;
  }

  function renderStatus(kind, message) {
    result.innerHTML = "";
    var box = document.createElement("div");
    box.className = "status " + kind;
    box.setAttribute("role", kind === "bad" ? "alert" : "status");
    box.textContent = message;
    result.appendChild(box);
  }

  function formatDateTime(value) {
    if (!value) return "không rõ thời điểm";
    var date = new Date(value);
    if (isNaN(date.getTime())) return "không rõ thời điểm";
    return date.toLocaleString("vi-VN");
  }

  function renderLead(lead, index) {
    result.innerHTML = "";

    var list = document.createElement("ul");
    list.className = "detail-list";

    var rows = [
      ["Khách", lead.full_name],
      ["Số điện thoại", util.formatPhone(lead.phone)],
      ["Dòng máy", lead.iphone_model],
      ["Màu ốp", lead.case_color],
      ["Trạng thái", lead.gift_status]
    ];

    rows.forEach(function (row) {
      var li = document.createElement("li");
      var strong = document.createElement("strong");
      strong.textContent = row[0] + ": ";
      li.appendChild(strong);
      li.appendChild(document.createTextNode(String(row[1] || "—")));
      list.appendChild(li);
    });

    result.appendChild(list);

    var button = document.createElement("button");
    button.type = "button";
    button.className = "primary-btn";
    button.id = "confirmRedeem";
    button.textContent = "XÁC NHẬN ĐÃ PHÁT QUÀ";
    button.addEventListener("click", function () {
      confirmRedeem(lead.gift_code, index);
    });
    result.appendChild(button);
  }

  function confirmRedeem(code, expectedIndex) {
    // Đọc lại ngay trước khi ghi: tab khác có thể vừa đổi trạng thái.
    var fresh = loadLeads();
    var index = findLeadIndex(fresh, code);

    if (index < 0) {
      renderStatus("bad", "Mã quà không còn tồn tại trên trình duyệt này.");
      return;
    }

    if (index !== expectedIndex) {
      renderStatus(
        "warn",
        "Dữ liệu đã thay đổi ở nơi khác. Vui lòng tra cứu lại mã trước khi phát quà."
      );
      return;
    }

    if (fresh[index].gift_status === "REDEEMED") {
      renderStatus(
        "warn",
        "Mã này đã được nhận quà lúc " + formatDateTime(fresh[index].redeemed_at) + ". Không phát lại."
      );
      return;
    }

    fresh[index].gift_status = "REDEEMED";
    fresh[index].redeemed_at = new Date().toISOString();
    fresh[index].redeemed_by = "LOCAL_STAFF (chưa xác thực)";

    if (!saveLeads(fresh)) {
      renderStatus("bad", "Không lưu được trạng thái trên trình duyệt này. Vui lòng thử lại.");
      return;
    }

    track("vipphone_gift_redeemed", {
      gift_code: util.normalizeGiftCode(code),
      gift_status: "REDEEMED"
    });

    renderStatus("ok", "Đã xác nhận phát quà thành công.");
  }

  function lookup(rawCode) {
    var code = util.normalizeGiftCode(rawCode);

    if (!code) {
      renderStatus("bad", "Vui lòng nhập mã nhận quà.");
      return;
    }

    if (!util.isWellFormedGiftCode(code)) {
      renderStatus("bad", "Mã quà không đúng định dạng VIP-YY-XXXXXX.");
      track("vipphone_gift_lookup_failed", { reason: "MALFORMED_CODE" });
      return;
    }

    var leads = loadLeads();
    var index = findLeadIndex(leads, code);

    if (index < 0) {
      renderStatus("bad", "Không tìm thấy mã quà trên trình duyệt này.");
      track("vipphone_gift_lookup_failed", { reason: "NOT_FOUND" });
      return;
    }

    var lead = leads[index];
    currentLead = lead;

    track("vipphone_gift_lookup", { gift_code: code, gift_status: lead.gift_status });

    if (lead.gift_status === "REDEEMED") {
      renderStatus(
        "warn",
        "Mã này đã được nhận quà lúc " + formatDateTime(lead.redeemed_at) + ". Không phát lại."
      );
      return;
    }

    renderLead(lead, index);
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    lookup(codeInput.value);
  });

  var initialCode = new URLSearchParams(window.location.search).get("code");
  if (initialCode) {
    codeInput.value = util.normalizeGiftCode(initialCode);
    lookup(initialCode);
  } else {
    codeInput.focus();
  }
})();
