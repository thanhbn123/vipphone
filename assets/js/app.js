const LEADS_KEY = "vipphone_leads_v1";
const LAST_GIFT_KEY = "vipphone_last_gift_code";
const form = document.getElementById("leadForm");
const modelSelect = document.getElementById("iphone_model");
const errorBox = document.getElementById("formError");
const submitBtn = document.getElementById("submitBtn");
let formStarted = false;

function track(event, extra = {}) {
  window.dataLayer = window.dataLayer || [];
  window.dataLayer.push({ event, ...extra });
}

function normalizePhone(value) {
  return value.replace(/\s+/g, "").replace(/[^\d+]/g, "");
}

function validVNPhone(value) {
  const p = normalizePhone(value);
  return /^(0|\+84)(3|5|7|8|9)\d{8}$/.test(p);
}

function randomGiftCode() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  let suffix = "";
  for (const b of bytes) suffix += alphabet[b % alphabet.length];
  return `VIP-26-${suffix}`;
}

function loadLeads() {
  try { return JSON.parse(localStorage.getItem(LEADS_KEY) || "[]"); }
  catch { return []; }
}

function getParams() {
  const p = new URLSearchParams(location.search);
  return {
    utm_source: p.get("utm_source") || "",
    utm_medium: p.get("utm_medium") || "",
    utm_campaign: p.get("utm_campaign") || "",
    utm_content: p.get("utm_content") || "",
    ref: p.get("ref") || "",
    src: p.get("src") || ""
  };
}

async function loadModels() {
  const res = await fetch("data/iphone-models.json", {cache: "no-store"});
  const groups = await res.json();
  modelSelect.innerHTML = '<option value="">Chọn dòng iPhone</option>';
  for (const group of groups) {
    if (!group.models.length) continue;
    const og = document.createElement("optgroup");
    og.label = String(group.year);
    for (const name of group.models) {
      const op = document.createElement("option");
      op.value = `${group.year}|${name}`;
      op.textContent = name;
      og.appendChild(op);
    }
    modelSelect.appendChild(og);
  }
}

form.addEventListener("focusin", () => {
  if (!formStarted) {
    formStarted = true;
    track("vipphone_form_start");
  }
}, { once: true });

form.addEventListener("submit", (e) => {
  e.preventDefault();
  errorBox.hidden = true;
  submitBtn.disabled = true;

  const fd = new FormData(form);
  const phone = normalizePhone(fd.get("phone") || "");
  const modelRaw = fd.get("iphone_model") || "";
  const [iphone_year, iphone_model] = modelRaw.split("|");
  const consent = fd.get("consent") === "on";

  if (!fd.get("full_name") || !phone || !modelRaw || !fd.get("case_color") || !consent) {
    errorBox.textContent = "Vui lòng điền đầy đủ các trường bắt buộc.";
    errorBox.hidden = false;
    submitBtn.disabled = false;
    return;
  }

  if (!validVNPhone(phone)) {
    errorBox.textContent = "Số điện thoại chưa đúng định dạng Việt Nam.";
    errorBox.hidden = false;
    submitBtn.disabled = false;
    return;
  }

  const leads = loadLeads();
  const recentDuplicate = leads.find(x => x.phone === phone && x.iphone_model === iphone_model && x.gift_status !== "CANCELLED");
  if (recentDuplicate) {
    localStorage.setItem(LAST_GIFT_KEY, recentDuplicate.gift_code);
    location.href = "success.html";
    return;
  }

  let gift_code;
  do { gift_code = randomGiftCode(); }
  while (leads.some(x => x.gift_code === gift_code));

  const q = getParams();
  const lead = {
    lead_id: crypto.randomUUID ? crypto.randomUUID() : `lead_${Date.now()}`,
    gift_code,
    full_name: String(fd.get("full_name") || "").trim(),
    phone,
    iphone_model,
    iphone_year: Number(iphone_year),
    case_color: String(fd.get("case_color") || ""),
    company_name: String(fd.get("company_name") || "").trim(),
    bni_chapter: String(fd.get("bni_chapter") || "").trim(),
    referrer_name: String(fd.get("referrer_name") || "").trim(),
    source: String(fd.get("source") || q.src || ""),
    campaign: q.utm_campaign,
    utm_source: q.utm_source,
    utm_medium: q.utm_medium,
    utm_campaign: q.utm_campaign,
    utm_content: q.utm_content,
    ref: q.ref,
    consent: true,
    created_at: new Date().toISOString(),
    gift_status: "NEW",
    redeemed_at: null,
    redeemed_by: null
  };

  leads.push(lead);
  localStorage.setItem(LEADS_KEY, JSON.stringify(leads));
  localStorage.setItem(LAST_GIFT_KEY, gift_code);

  track("vipphone_lead_submit", { iphone_model, source: lead.source });
  track("vipphone_gift_code_created", { gift_code });

  location.href = "success.html";
});

loadModels().catch(() => {
  modelSelect.innerHTML = '<option value="">Không tải được danh sách máy</option>';
  errorBox.textContent = "Không tải được danh sách iPhone. Hãy chạy qua web server thay vì mở file trực tiếp.";
  errorBox.hidden = false;
});
