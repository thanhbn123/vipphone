const LEADS_KEY = "vipphone_leads_v1";
const LAST_GIFT_KEY = "vipphone_last_gift_code";
const code = localStorage.getItem(LAST_GIFT_KEY);
const leads = JSON.parse(localStorage.getItem(LEADS_KEY) || "[]");
const lead = leads.find(x => x.gift_code === code);

if (!lead) {
  document.getElementById("giftDetails").innerHTML = "<p>Không tìm thấy thông tin đăng ký trên trình duyệt này.</p>";
} else {
  document.getElementById("giftCode").textContent = lead.gift_code;
  document.getElementById("giftDetails").innerHTML = `
    <strong>${escapeHtml(lead.full_name)}</strong><br>
    ${escapeHtml(lead.iphone_model)} · ${escapeHtml(lead.case_color)}
  `;
  const redeemUrl = new URL("redeem.html", location.href);
  redeemUrl.searchParams.set("code", lead.gift_code);
  drawQrLike(document.getElementById("qr"), redeemUrl.toString(), 220);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}
