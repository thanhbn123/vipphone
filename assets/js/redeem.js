const LEADS_KEY = "vipphone_leads_v1";
const form = document.getElementById("redeemForm");
const codeInput = document.getElementById("redeemCode");
const result = document.getElementById("redeemResult");

const initialCode = new URLSearchParams(location.search).get("code");
if (initialCode) codeInput.value = initialCode;

function loadLeads() {
  try { return JSON.parse(localStorage.getItem(LEADS_KEY) || "[]"); }
  catch { return []; }
}

function saveLeads(leads) {
  localStorage.setItem(LEADS_KEY, JSON.stringify(leads));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const code = codeInput.value.trim().toUpperCase();
  const leads = loadLeads();
  const idx = leads.findIndex(x => x.gift_code === code);

  if (idx < 0) {
    result.innerHTML = '<div class="status bad">Không tìm thấy mã quà.</div>';
    return;
  }

  const lead = leads[idx];
  if (lead.gift_status === "REDEEMED") {
    result.innerHTML = `<div class="status warn">Mã này đã được nhận quà lúc ${new Date(lead.redeemed_at).toLocaleString("vi-VN")}.</div>`;
    return;
  }

  result.innerHTML = `
    <ul class="detail-list">
      <li><strong>Khách:</strong> ${escapeHtml(lead.full_name)}</li>
      <li><strong>Điện thoại:</strong> ${escapeHtml(lead.iphone_model)}</li>
      <li><strong>Màu ốp:</strong> ${escapeHtml(lead.case_color)}</li>
      <li><strong>Trạng thái:</strong> ${escapeHtml(lead.gift_status)}</li>
    </ul>
    <button id="confirmRedeem" class="primary-btn">XÁC NHẬN ĐÃ PHÁT QUÀ</button>
  `;

  document.getElementById("confirmRedeem").addEventListener("click", () => {
    const fresh = loadLeads();
    const freshIdx = fresh.findIndex(x => x.gift_code === code);
    if (freshIdx < 0 || fresh[freshIdx].gift_status === "REDEEMED") {
      result.innerHTML = '<div class="status warn">Mã đã thay đổi trạng thái hoặc không còn hợp lệ.</div>';
      return;
    }
    fresh[freshIdx].gift_status = "REDEEMED";
    fresh[freshIdx].redeemed_at = new Date().toISOString();
    fresh[freshIdx].redeemed_by = "LOCAL_STAFF";
    saveLeads(fresh);

    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({event:"vipphone_gift_redeemed", gift_code: code});
    result.innerHTML = '<div class="status ok">Đã xác nhận phát quà thành công.</div>';
  });
});

if (initialCode) {
  form.requestSubmit();
}
