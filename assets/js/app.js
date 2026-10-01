/*!
 * VIP PHONE — landing: thu lead, sinh gift code, chuyển trang thành công
 *
 * ⚠️  BẢN DEMO CLIENT-ONLY.
 * Dữ liệu lưu trong `localStorage` của CHÍNH trình duyệt này. Nhân viên ở máy
 * khác KHÔNG nhìn thấy lead. Không có kiểm tra phía server, không có rate
 * limit, không có nguồn chân lý. Từ G02 toàn bộ việc này chuyển về server.
 */
"use strict";

(function () {
  var LEADS_KEY = "vipphone_leads_v1";
  var LAST_GIFT_KEY = "vipphone_last_gift_code";
  var GIFT_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // bỏ I, O, 0, 1
  var GIFT_CODE_LENGTH = 6;
  var MODEL_SEPARATOR = "|";

  var form = document.getElementById("leadForm");
  var modelSelect = document.getElementById("iphone_model");
  var errorBox = document.getElementById("formError");
  var submitBtn = document.getElementById("submitBtn");
  var submitLabel = submitBtn ? submitBtn.textContent : "GỬI";

  var formStarted = false;
  var submitting = false;
  var catalogReady = false;

  if (!form || !modelSelect || !submitBtn) return;

  var track = window.VPTrack.track;
  var util = window.VPUtil;

  /* ------------------------------------------------------------------ */
  /* Thông báo lỗi cấp form                                              */
  /* ------------------------------------------------------------------ */

  function showFormError(message) {
    if (!errorBox) return;
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  function clearFormError() {
    if (!errorBox) return;
    errorBox.textContent = "";
    errorBox.hidden = true;
  }

  /* ------------------------------------------------------------------ */
  /* Thông báo lỗi cấp trường                                            */
  /* ------------------------------------------------------------------ */

  function errorIdFor(field) {
    return "error-" + field.name;
  }

  function setFieldError(field, message) {
    var existing = document.getElementById(errorIdFor(field));
    if (!existing) {
      existing = document.createElement("span");
      existing.className = "field-error";
      existing.id = errorIdFor(field);
      existing.setAttribute("role", "alert");
      field.insertAdjacentElement("afterend", existing);
    }
    existing.textContent = message;
    field.setAttribute("aria-invalid", "true");
    field.setAttribute("aria-describedby", existing.id);
    field.classList.add("has-error");
  }

  function clearFieldError(field) {
    var existing = document.getElementById(errorIdFor(field));
    if (existing) existing.remove();
    field.removeAttribute("aria-invalid");
    field.removeAttribute("aria-describedby");
    field.classList.remove("has-error");
  }

  function clearAllFieldErrors() {
    Array.prototype.forEach.call(form.elements, function (el) {
      if (el.name) clearFieldError(el);
    });
  }

  /* ------------------------------------------------------------------ */
  /* Validation                                                          */
  /* ------------------------------------------------------------------ */

  function readForm() {
    var fd = new FormData(form);
    var modelRaw = String(fd.get("iphone_model") || "");
    var parts = modelRaw.split(MODEL_SEPARATOR);
    return {
      full_name: String(fd.get("full_name") || "").trim(),
      phone: util.normalizePhone(fd.get("phone")),
      iphone_year: parts.length === 2 ? Number(parts[0]) : NaN,
      iphone_model: parts.length === 2 ? parts[1] : "",
      case_color: String(fd.get("case_color") || ""),
      company_name: String(fd.get("company_name") || "").trim(),
      bni_chapter: String(fd.get("bni_chapter") || "").trim(),
      referrer_name: String(fd.get("referrer_name") || "").trim(),
      source: String(fd.get("source") || ""),
      consent: fd.get("consent") === "on"
    };
  }

  /**
   * Trả về map {tên_trường: thông_báo_lỗi}. Rỗng = hợp lệ.
   * Độ dài được kiểm lại ở đây — KHÔNG tin `maxlength` của HTML, nó sửa được.
   */
  function validate(data) {
    var errors = {};

    if (!data.full_name) errors.full_name = "Vui lòng nhập họ và tên.";
    else if (data.full_name.length > 80) errors.full_name = "Họ và tên tối đa 80 ký tự.";

    if (!data.phone) errors.phone = "Vui lòng nhập số điện thoại.";
    else if (!util.isValidVnMobile(data.phone)) {
      errors.phone =
        "Số điện thoại chưa đúng định dạng Việt Nam (10 số, bắt đầu bằng 03/05/07/08/09).";
    }

    if (!data.iphone_model) errors.iphone_model = "Vui lòng chọn dòng iPhone.";
    if (!Number.isInteger(data.iphone_year) || data.iphone_year < 2007) {
      errors.iphone_year = "Năm của dòng máy không hợp lệ.";
    }

    if (!data.case_color) errors.case_color = "Vui lòng chọn màu ốp.";
    if (data.company_name.length > 120) errors.company_name = "Tên công ty tối đa 120 ký tự.";
    if (data.bni_chapter.length > 80) errors.bni_chapter = "Chapter BNI tối đa 80 ký tự.";
    if (data.referrer_name.length > 80) errors.referrer_name = "Người giới thiệu tối đa 80 ký tự.";
    if (!data.consent) errors.consent = "Cần đồng ý để VIP PHONE liên hệ xác nhận quà.";

    return errors;
  }

  function focusFirstError(errors) {
    var order = [
      "full_name",
      "phone",
      "iphone_model",
      "case_color",
      "company_name",
      "bni_chapter",
      "referrer_name",
      "source",
      "consent"
    ];
    for (var i = 0; i < order.length; i++) {
      if (errors[order[i]]) {
        var el = form.elements[order[i]];
        if (el && typeof el.focus === "function") {
          el.focus();
          return;
        }
      }
    }
  }

  /* ------------------------------------------------------------------ */
  /* Ghi / đọc localStorage                                              */
  /* ------------------------------------------------------------------ */

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

  function rememberGiftCode(code) {
    try {
      localStorage.setItem(LAST_GIFT_KEY, code);
    } catch (err) {
      /* chế độ riêng tư — bỏ qua */
    }
  }

  /* ------------------------------------------------------------------ */
  /* Gift code                                                           */
  /* ------------------------------------------------------------------ */

  function randomGiftCode() {
    var bytes = new Uint8Array(GIFT_CODE_LENGTH);
    crypto.getRandomValues(bytes);
    var suffix = "";
    for (var i = 0; i < bytes.length; i++) {
      suffix += GIFT_CODE_ALPHABET[bytes[i] % GIFT_CODE_ALPHABET.length];
    }
    return "VIP-" + util.giftYearPrefix() + "-" + suffix;
  }

  function newLeadId() {
    if (window.crypto && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    var bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.prototype.map
      .call(bytes, function (b) { return ("0" + b.toString(16)).slice(-2); })
      .join("");
  }

  /* ------------------------------------------------------------------ */
  /* Danh mục iPhone                                                     */
  /* ------------------------------------------------------------------ */

  function setCatalogUnavailable(message) {
    catalogReady = false;
    modelSelect.innerHTML = "";
    var option = document.createElement("option");
    option.value = "";
    option.textContent = "Không tải được danh sách máy";
    modelSelect.appendChild(option);
    modelSelect.disabled = true;
    showFormError(message);
  }

  function loadModels() {
    return fetch("data/iphone-models.json", { cache: "no-store" })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (groups) {
        if (!Array.isArray(groups)) throw new Error("Định dạng danh mục không hợp lệ.");

        modelSelect.innerHTML = "";
        var placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Chọn dòng iPhone";
        modelSelect.appendChild(placeholder);

        var modelCount = 0;
        groups.forEach(function (group) {
          var models = Array.isArray(group.models) ? group.models : [];
          if (!models.length) return;

          var optgroup = document.createElement("optgroup");
          optgroup.label = String(group.year);
          models.forEach(function (name) {
            var option = document.createElement("option");
            option.value = group.year + MODEL_SEPARATOR + name;
            option.textContent = String(name);
            optgroup.appendChild(option);
            modelCount++;
          });
          modelSelect.appendChild(optgroup);
        });

        if (modelCount === 0) throw new Error("Danh mục rỗng.");
        modelSelect.disabled = false;
        catalogReady = true;
        submitBtn.disabled = false;
      })
      .catch(function () {
        setCatalogUnavailable(
          "Không tải được danh sách iPhone. Hãy chạy qua web server thay vì mở file trực tiếp, rồi tải lại trang."
        );
      });
  }

  /* ------------------------------------------------------------------ */
  /* Submit                                                              */
  /* ------------------------------------------------------------------ */

  function setSubmitting(state) {
    submitting = state;
    submitBtn.disabled = state || !catalogReady;
    submitBtn.setAttribute("aria-busy", state ? "true" : "false");
    submitBtn.textContent = state ? "ĐANG GỬI…" : submitLabel;
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (submitting) return; // chống double submit

    clearFormError();
    clearAllFieldErrors();

    var data = readForm();
    var errors = validate(data);

    if (Object.keys(errors).length) {
      Object.keys(errors).forEach(function (name) {
        var field = form.elements[name];
        if (field) setFieldError(field, errors[name]);
      });
      showFormError("Vui lòng kiểm tra lại các trường được đánh dấu.");
      focusFirstError(errors);
      return;
    }

    setSubmitting(true);

    var attribution = window.VPTrack.getAttribution();
    var leads = loadLeads();

    // Chống trùng phía client — chỉ là tiện ích cho người dùng.
    // Từ G02, SERVER mới là nơi quyết định (xem DUPLICATE POLICY ở MASTER_STATUS).
    var duplicate = leads.find(function (lead) {
      return (
        util.normalizePhone(lead.phone) === data.phone &&
        lead.iphone_model === data.iphone_model &&
        lead.gift_status !== "CANCELLED"
      );
    });

    if (duplicate) {
      rememberGiftCode(duplicate.gift_code);
      window.location.href = "success.html";
      return;
    }

    var giftCode = randomGiftCode();
    var attempts = 0;
    while (
      leads.some(function (lead) { return lead.gift_code === giftCode; }) &&
      attempts < 10
    ) {
      giftCode = randomGiftCode();
      attempts++;
    }

    var lead = {
      lead_id: newLeadId(),
      gift_code: giftCode,
      full_name: data.full_name,
      phone: data.phone,
      iphone_model: data.iphone_model,
      iphone_year: data.iphone_year,
      case_color: data.case_color,
      company_name: data.company_name,
      bni_chapter: data.bni_chapter,
      referrer_name: data.referrer_name,
      source: data.source || attribution.src || "",
      campaign: attribution.campaign || attribution.utm_campaign || "",
      utm_source: attribution.utm_source || "",
      utm_medium: attribution.utm_medium || "",
      utm_campaign: attribution.utm_campaign || "",
      utm_content: attribution.utm_content || "",
      ref: attribution.ref || "",
      consent: true,
      gift_status: "NEW",
      created_at: new Date().toISOString(),
      redeemed_at: null,
      redeemed_by: null
    };

    leads.push(lead);

    if (!saveLeads(leads)) {
      showFormError(
        "Không lưu được thông tin trên trình duyệt này (bộ nhớ trình duyệt đầy hoặc đang ở chế độ riêng tư). Vui lòng thử lại ở cửa sổ thường."
      );
      setSubmitting(false);
      return;
    }

    rememberGiftCode(giftCode);

    track("vipphone_lead_submit", {
      iphone_model: data.iphone_model,
      iphone_year: data.iphone_year,
      source: lead.source,
      utm_source: lead.utm_source,
      utm_campaign: lead.utm_campaign
    });
    track("vipphone_gift_code_created", {
      gift_code: giftCode,
      iphone_model: data.iphone_model
    });

    window.location.href = "success.html";
  }

  /* ------------------------------------------------------------------ */
  /* Khởi động                                                           */
  /* ------------------------------------------------------------------ */

  form.addEventListener(
    "focusin",
    function () {
      if (formStarted) return;
      formStarted = true;
      track("vipphone_form_start");
    },
    { once: true }
  );

  form.addEventListener("submit", handleSubmit);

  // Xoá lỗi của một trường ngay khi người dùng sửa nó.
  form.addEventListener("input", function (event) {
    if (event.target && event.target.name) clearFieldError(event.target);
  });
  form.addEventListener("change", function (event) {
    if (event.target && event.target.name) clearFieldError(event.target);
  });

  submitBtn.disabled = true; // chỉ bật khi danh mục máy đã sẵn sàng
  loadModels();
})();
