/*!
 * VIP PHONE — landing: thu lead qua API thật.
 *
 * Khác biệt so với bản client-only trước đây:
 * - KHÔNG dùng `localStorage` làm nơi lưu lead. Server + PostgreSQL là nguồn
 *   chân lý duy nhất.
 * - Server tự chuẩn hoá số điện thoại, tự tra dòng máy trong danh mục, tự
 *   quyết định chuyện trùng lặp. Frontend chỉ kiểm trước cho phản hồi nhanh.
 * - Danh mục iPhone đọc từ `/api/catalog/iphone-models`, không hard-code.
 */
"use strict";

(function () {
  var RESULT_KEY = "vipphone_last_gift_v1";

  var form = document.getElementById("leadForm");
  var modelSelect = document.getElementById("iphone_model");
  var errorBox = document.getElementById("formError");
  var turnstileWrap = document.getElementById("turnstileWrap");
  var turnstileWidget = document.getElementById("turnstileWidget");
  var submitBtn = document.getElementById("submitBtn");
  var submitLabel = submitBtn ? submitBtn.textContent : "GỬI";

  if (!form || !modelSelect || !submitBtn) return;

  var track = window.VPTrack.track;
  var util = window.VPUtil;
  var config = window.VIPPHONE_CONFIG || {};

  var turnstile = null;
  var formStarted = false;
  var submitting = false;
  var catalogReady = false;

  function apiBase() {
    return config.apiBase || "";
  }

  /* ------------------------------------------------------------ thông báo */

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

  /* ----------------------------------------------------------- đọc dữ liệu */

  function readForm() {
    var fd = new FormData(form);
    return {
      full_name: String(fd.get("full_name") || "").trim(),
      phone: util.normalizePhone(fd.get("phone")),
      iphone_model: String(fd.get("iphone_model") || ""),
      case_color: String(fd.get("case_color") || ""),
      email: String(fd.get("email") || "").trim(),
      address_street: String(fd.get("address_street") || "").trim(),
      address_ward: String(fd.get("address_ward") || "").trim(),
      address_district: String(fd.get("address_district") || "").trim(),
      address_province: String(fd.get("address_province") || "").trim(),
      bni_chapter: String(fd.get("bni_chapter") || "").trim(),
      referrer_name: String(fd.get("referrer_name") || "").trim(),
      source: String(fd.get("source") || ""),
      consent: fd.get("consent") === "on"
    };
  }

  /** Kiểm tra trước ở client — CHỈ để phản hồi nhanh. Server vẫn kiểm lại. */
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
    if (data.bni_chapter.length > 80) errors.bni_chapter = "Chapter BNI tối đa 80 ký tự.";
    if (data.referrer_name.length > 80) errors.referrer_name = "Người giới thiệu tối đa 80 ký tự.";
    if (!data.consent) errors.consent = "Cần đồng ý để VIP PHONE liên hệ xác nhận quà.";

    return errors;
  }

  var FIELD_ORDER = [
    "full_name",
    "phone",
    "iphone_model",
    "case_color",
    "email",
    "address_street",
    "address_ward",
    "address_district",
    "address_province",
    "bni_chapter",
    "referrer_name",
    "source",
    "consent"
  ];

  function showFieldErrors(errors) {
    Object.keys(errors).forEach(function (name) {
      var field = form.elements[name];
      if (field) setFieldError(field, errors[name]);
    });

    for (var i = 0; i < FIELD_ORDER.length; i++) {
      if (errors[FIELD_ORDER[i]]) {
        var el = form.elements[FIELD_ORDER[i]];
        if (el && typeof el.focus === "function") {
          el.focus();
          return;
        }
      }
    }
  }

  /* -------------------------------------------------------------- danh mục */

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
    var controller = new AbortController();
    var timer = window.setTimeout(function () {
      controller.abort();
    }, config.requestTimeoutMs || 15000);

    return fetch(apiBase() + "/api/catalog/iphone-models", {
      cache: "no-store",
      signal: controller.signal
    })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (models) {
        if (!Array.isArray(models) || !models.length) {
          throw new Error("Danh mục rỗng.");
        }

        modelSelect.innerHTML = "";
        var placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Chọn dòng iPhone";
        modelSelect.appendChild(placeholder);

        var groups = {};
        var order = [];
        models.forEach(function (model) {
          var year = String(model.year);
          if (!groups[year]) {
            groups[year] = [];
            order.push(year);
          }
          groups[year].push(model);
        });

        order.forEach(function (year) {
          var optgroup = document.createElement("optgroup");
          optgroup.label = year;
          groups[year].forEach(function (model) {
            var option = document.createElement("option");
            option.value = model.model_code;
            option.textContent = model.display_name;
            optgroup.appendChild(option);
          });
          modelSelect.appendChild(optgroup);
        });

        modelSelect.disabled = false;
        catalogReady = true;
        submitBtn.disabled = false;
      })
      .catch(function () {
        setCatalogUnavailable(
          "Không tải được danh sách iPhone. Vui lòng kiểm tra kết nối rồi tải lại trang."
        );
      })
      .finally(function () {
        window.clearTimeout(timer);
      });
  }

  /* ---------------------------------------------------------------- submit */

  function setSubmitting(state) {
    submitting = state;
    submitBtn.disabled = state || !catalogReady;
    submitBtn.setAttribute("aria-busy", state ? "true" : "false");
    submitBtn.textContent = state ? "ĐANG GỬI…" : submitLabel;
  }

  function selectedModelName() {
    var option = modelSelect.options[modelSelect.selectedIndex];
    return option ? option.textContent : "";
  }

  function rememberResult(result) {
    try {
      sessionStorage.setItem(
        RESULT_KEY,
        JSON.stringify({
          lead_id: result.lead_id,
          gift_code: result.gift_code,
          gift_status: result.gift_status,
          duplicate: result.duplicate === true,
          // Chỉ lưu trường cần hiển thị lại. KHÔNG lưu số điện thoại.
          full_name: String(form.elements.full_name.value).trim(),
          iphone_model: selectedModelName(),
          case_color: String(form.elements.case_color.value)
        })
      );
    } catch (err) {
      /* chế độ riêng tư — trang thành công sẽ hiện hướng dẫn thay thế */
    }
  }

  function readApiError(response) {
    return response
      .json()
      .catch(function () {
        return {};
      })
      .then(function (body) {
        var error = body && body.error ? body.error : {};
        return {
          message: error.message || "Có lỗi xảy ra. Vui lòng thử lại.",
          fields: error.fields || {}
        };
      });
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (submitting) return; // chống double submit

    // Turnstile BẬT mà chưa có token thì gửi lên chắc chắn bị 403. Nói ngay tại
    // chỗ thay vì để khách nhận lỗi khó hiểu từ server.
    if (turnstile && turnstile.isEnabled() && !turnstile.getToken()) {
      showFormError(
        turnstile.hasFailed()
          ? "Không tải được bước kiểm tra chống spam. Vui lòng tải lại trang rồi thử lại."
          : "Vui lòng hoàn tất bước kiểm tra chống spam ở trên rồi bấm gửi."
      );
      return;
    }

    clearFormError();
    clearAllFieldErrors();

    var data = readForm();
    var localErrors = validate(data);

    if (Object.keys(localErrors).length) {
      showFieldErrors(localErrors);
      showFormError("Vui lòng kiểm tra lại các trường được đánh dấu.");
      return;
    }

    setSubmitting(true);

    var attribution = window.VPTrack.getAttribution();
    var payload = {
      full_name: data.full_name,
      phone: data.phone,
      iphone_model: data.iphone_model,
      // Ô ghi chú màu không bắt buộc: để trống gửi null để DB lưu NULL.
      case_color: data.case_color || null,
      // Trường KHÔNG bắt buộc: gửi null khi bỏ trống để DB lưu NULL, không lưu chuỗi rỗng.
      email: data.email || null,
      address_street: data.address_street || null,
      address_ward: data.address_ward || null,
      address_district: data.address_district || null,
      address_province: data.address_province || null,
      bni_chapter: data.bni_chapter || null,
      referrer_name: data.referrer_name || null,
      source: data.source || attribution.src || null,
      campaign: attribution.campaign || attribution.utm_campaign || null,
      utm_source: attribution.utm_source || null,
      utm_medium: attribution.utm_medium || null,
      utm_campaign: attribution.utm_campaign || null,
      utm_content: attribution.utm_content || null,
      ref: attribution.ref || null,
      consent: data.consent === true,
      // Chỉ gửi khi có. Server tự quyết định có bắt buộc hay không.
      turnstile_token: turnstile ? turnstile.getToken() : null
    };

    fetch(apiBase() + "/api/leads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (response) {
        if (response.status === 201) {
          return response.json().then(function (result) {
            track("vipphone_lead_submit", {
              iphone_model: data.iphone_model,
              source: payload.source,
              utm_source: payload.utm_source,
              utm_campaign: payload.utm_campaign,
              duplicate: result.duplicate === true
            });
            track("vipphone_gift_code_created", {
              gift_code: result.gift_code,
              iphone_model: data.iphone_model
            });
            rememberResult(result);
            window.location.href = "success.html";
          });
        }

        return readApiError(response).then(function (error) {
          if (response.status === 422 && Object.keys(error.fields).length) {
            showFieldErrors(error.fields);
            showFormError("Vui lòng kiểm tra lại các trường được đánh dấu.");
          } else if (response.status === 429) {
            showFormError(
              "Bạn vừa gửi quá nhiều lần. Vui lòng đợi một lát rồi thử lại."
            );
          } else if (response.status === 403) {
            if (turnstile) turnstile.reset();
            showFormError(
              "Không qua được bước kiểm tra chống spam. Vui lòng thử lại."
            );
          } else {
            showFormError(error.message);
          }
          setSubmitting(false);
        });
      })
      .catch(function () {
        showFormError(
          "Không kết nối được máy chủ. Vui lòng kiểm tra mạng rồi thử lại."
        );
        setSubmitting(false);
      });
  }

  /* -------------------------------------------------------------- khởi động */

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

  form.addEventListener("input", function (event) {
    if (event.target && event.target.name) clearFieldError(event.target);
  });
  form.addEventListener("change", function (event) {
    if (event.target && event.target.name) clearFieldError(event.target);
  });

  submitBtn.disabled = true; // chỉ bật khi danh mục máy đã sẵn sàng
  loadModels();

  // Turnstile là TUỲ CHỌN: tắt thì hàm init trả về ngay và không nạp gì từ Internet.
  // Không chờ nó xong mới bật form — nạp mạng chậm không được làm chậm trang.
  turnstile = window.VPTurnstile || null;
  if (turnstile) {
    turnstile.init(turnstileWidget).then(function () {
      if (turnstile.isEnabled() && turnstileWrap) {
        turnstileWrap.hidden = false;
      }
    });
  }
})();
