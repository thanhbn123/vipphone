/*!
 * VIP PHONE — trang quản trị lead (G05) và danh mục iPhone (G06).
 *
 * QUY TẮC BẮT BUỘC CỦA FILE NÀY:
 *
 * 1. **Không dùng `innerHTML` cho dữ liệu.** Mọi nội dung lấy từ API (tên khách,
 *    tên công ty, UTM…) đều được ghi bằng `textContent` hoặc `createTextNode`.
 *    Đó là cách escape chắc nhất: không có chuỗi nào được diễn giải thành HTML,
 *    nên không có đường XSS nào để hở. CSP `script-src 'self'` là lớp thứ hai.
 * 2. **Khoá nhân viên chỉ vào `sessionStorage`** (`vipphone_staff_key_v1`), dùng
 *    chung với trang /redeem. KHÔNG `localStorage`, KHÔNG cookie, KHÔNG query
 *    string (query string đi vào log máy chủ và lịch sử trình duyệt).
 * 3. **Export CSV đi qua `fetch` có header**, không phải link `<a href>`, vì
 *    link không gửi được `X-Staff-Key`. Đổi sang link là vừa hỏng xác thực vừa
 *    buộc phải nhét khoá vào URL.
 */
"use strict";

(function () {
  var STAFF_KEY_STORAGE = "vipphone_staff_key_v1";

  var config = window.VIPPHONE_CONFIG || {};

  var keyInput = document.getElementById("staffKey");
  var filterForm = document.getElementById("filterForm");
  var statusLine = document.getElementById("statusLine");
  var errorBox = document.getElementById("errorBox");
  var leadRows = document.getElementById("leadRows");
  var pageInfo = document.getElementById("pageInfo");
  var prevBtn = document.getElementById("prevBtn");
  var nextBtn = document.getElementById("nextBtn");
  var detailBox = document.getElementById("detailBox");
  var exportBtn = document.getElementById("exportBtn");
  var resetBtn = document.getElementById("resetBtn");
  var modelSelect = document.getElementById("fModel");
  var modelForm = document.getElementById("modelForm");
  var modelRows = document.getElementById("modelRows");
  var modelStatus = document.getElementById("modelStatus");
  var modelError = document.getElementById("modelError");

  if (!filterForm || !leadRows) return;

  var state = { page: 1, pageSize: 50, total: 0, lastParams: null, catalogLoaded: false };

  /* ------------------------------------------------------------- tiện ích */

  function apiBase() {
    return config.apiBase || "";
  }

  function readKey() {
    if (keyInput && keyInput.value.trim()) return keyInput.value.trim();
    try {
      return sessionStorage.getItem(STAFF_KEY_STORAGE) || "";
    } catch (err) {
      return "";
    }
  }

  function rememberKey(key) {
    if (!key) return;
    try {
      // CHỈ sessionStorage — khoá không được sống lâu hơn phiên của tab này.
      sessionStorage.setItem(STAFF_KEY_STORAGE, key);
    } catch (err) {
      /* chế độ riêng tư */
    }
  }

  function setStatus(message) {
    if (statusLine) statusLine.textContent = message || "";
  }

  function showError(message) {
    if (!errorBox) return;
    errorBox.textContent = message;
    errorBox.hidden = !message;
  }

  function setModelStatus(message) {
    if (modelStatus) modelStatus.textContent = message || "";
  }

  function showModelError(message) {
    if (!modelError) return;
    modelError.textContent = message;
    modelError.hidden = !message;
  }

  function formatDateTime(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (isNaN(date.getTime())) return "—";
    return date.toLocaleString("vi-VN");
  }

  /** Gọi API quản trị kèm khoá. Trả `{ok, status, body}` — KHÔNG ném ra ngoài. */
  function callApi(path, options) {
    var opts = options || {};
    var headers = opts.headers || {};
    var key = readKey();
    if (key) headers["X-Staff-Key"] = key;

    return fetch(apiBase() + path, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body
    })
      .then(function (response) {
        if (response.status === 401) {
          return { ok: false, status: 401, body: null, response: response };
        }
        if (response.status === 503) {
          return { ok: false, status: 503, body: null, response: response };
        }
        if (opts.raw) {
          return { ok: response.ok, status: response.status, response: response, body: null };
        }
        return response
          .json()
          .catch(function () {
            return null;
          })
          .then(function (body) {
            return { ok: response.ok, status: response.status, body: body, response: response };
          });
      })
      .catch(function () {
        return { ok: false, status: 0, body: null, response: null };
      });
  }

  function explainFailure(result, fallback) {
    if (result.status === 401) {
      return "Khoá truy cập nhân viên không hợp lệ hoặc còn thiếu. Nhập khoá ở ô phía trên rồi thử lại.";
    }
    if (result.status === 503) {
      return "Máy chủ chưa cấu hình xác thực nhân viên (STAFF_API_KEYS), nên khu vực quản trị đang đóng.";
    }
    if (result.status === 0) {
      return "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.";
    }
    return fallback;
  }

  function fieldErrorOf(body) {
    if (body && body.error && body.error.fields) {
      var parts = [];
      Object.keys(body.error.fields).forEach(function (name) {
        parts.push(name + ": " + body.error.fields[name]);
      });
      if (parts.length) return parts.join(" · ");
    }
    if (body && body.error && body.error.message) return body.error.message;
    return "";
  }

  /* ------------------------------------------------------- bộ lọc + bảng */

  function currentFilters() {
    var fd = new FormData(filterForm);
    return {
      phone: String(fd.get("phone") || "").trim(),
      iphone_model: String(fd.get("iphone_model") || "").trim(),
      source: String(fd.get("source") || "").trim(),
      gift_status: String(fd.get("gift_status") || "").trim(),
      created_from: String(fd.get("created_from") || "").trim(),
      created_to: String(fd.get("created_to") || "").trim(),
      page_size: String(fd.get("page_size") || "50")
    };
  }

  function filterParams(page) {
    var filters = currentFilters();
    var params = new URLSearchParams();
    ["phone", "iphone_model", "source", "gift_status", "created_from", "created_to"].forEach(
      function (name) {
        if (filters[name]) params.set(name, filters[name]);
      }
    );
    params.set("page", String(page));
    params.set("page_size", filters.page_size);
    return params;
  }

  function cell(text, className) {
    var td = document.createElement("td");
    if (className) td.className = className;
    td.textContent = text === null || text === undefined || text === "" ? "—" : String(text);
    return td;
  }

  function renderRows(items) {
    leadRows.innerHTML = "";

    if (!items.length) {
      var empty = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 8;
      td.textContent = "Không có lead nào khớp bộ lọc.";
      empty.appendChild(td);
      leadRows.appendChild(empty);
      return;
    }

    items.forEach(function (lead) {
      var tr = document.createElement("tr");
      tr.appendChild(cell(lead.gift_code));
      tr.appendChild(cell(lead.full_name));
      tr.appendChild(cell(lead.phone));
      tr.appendChild(cell(lead.iphone_model));
      tr.appendChild(cell(lead.source));
      tr.appendChild(cell(lead.gift_status));
      tr.appendChild(cell(formatDateTime(lead.created_at)));

      var actionCell = document.createElement("td");
      var button = document.createElement("button");
      button.type = "button";
      button.className = "secondary-btn small-btn";
      button.textContent = "Xem";
      button.setAttribute("aria-label", "Xem chi tiết lead " + lead.gift_code);
      button.addEventListener("click", function () {
        showDetail(lead.lead_id);
      });
      actionCell.appendChild(button);
      tr.appendChild(actionCell);

      leadRows.appendChild(tr);
    });
  }

  function loadLeads(page) {
    var target = page || 1;
    var params = filterParams(target);
    state.pageSize = Number(currentFilters().page_size);

    setStatus("Đang tải…");
    showError("");

    callApi("/api/admin/leads?" + params.toString()).then(function (result) {
      if (!result.ok || !result.body) {
        setStatus("");
        showError(explainFailure(result, "Không tải được danh sách lead."));
        return;
      }

      rememberKey(readKey());
      state.page = result.body.page;
      state.total = result.body.total;
      state.lastParams = params;

      renderRows(result.body.items);
      updatePager();
      setStatus(
        "Tìm thấy " + state.total + " lead. Đang xem trang " + state.page + "."
      );

      // Khoá nhập SAU khi trang đã mở thì bảng danh mục còn trống. Nạp một lần
      // ngay tại đây — nếu không, người dùng phải tải lại trang mới thấy danh
      // mục, và đó là lỗi im lặng: bảng trống trông y như "danh mục rỗng".
      //
      // Chỉ nạp MỘT lần: `loadModels()` dựng lại ô chọn dòng máy, nạp lại nhiều
      // lần sẽ xoá lựa chọn bộ lọc người dùng vừa đặt.
      if (!state.catalogLoaded) {
        state.catalogLoaded = true;
        loadModels();
      }
    });
  }

  function updatePager() {
    var pageSize = state.pageSize || 50;
    var totalPages = Math.max(1, Math.ceil(state.total / pageSize));
    pageInfo.textContent = "Trang " + state.page + "/" + totalPages + " — " + state.total + " lead";
    prevBtn.disabled = state.page <= 1;
    nextBtn.disabled = state.page >= totalPages;
  }

  /* --------------------------------------------------------------- chi tiết */

  function detailRow(label, value) {
    var li = document.createElement("li");
    var strong = document.createElement("strong");
    strong.textContent = label + ": ";
    li.appendChild(strong);
    li.appendChild(document.createTextNode(value === null || value === undefined || value === "" ? "—" : String(value)));
    return li;
  }

  function showDetail(leadId) {
    detailBox.textContent = "Đang tải chi tiết…";

    callApi("/api/admin/leads/" + encodeURIComponent(leadId)).then(function (result) {
      detailBox.innerHTML = "";

      if (!result.ok || !result.body) {
        var box = document.createElement("div");
        box.className = "status bad";
        box.setAttribute("role", "alert");
        box.textContent =
          result.status === 404
            ? "Không tìm thấy lead này."
            : explainFailure(result, "Không tải được chi tiết lead.");
        detailBox.appendChild(box);
        return;
      }

      var lead = result.body;
      var list = document.createElement("ul");
      list.className = "detail-list";
      [
        ["Mã quà", lead.gift_code],
        ["Khách", lead.full_name],
        ["Số điện thoại", lead.phone],
        ["Dòng máy", lead.iphone_model + " (" + lead.iphone_year + ")"],
        ["Màu ốp", lead.case_color],
        ["Công ty", lead.company_name],
        ["Chapter BNI", lead.bni_chapter],
        ["Người giới thiệu", lead.referrer_name],
        ["Nguồn", lead.source],
        ["Chiến dịch", lead.campaign],
        ["UTM source", lead.utm_source],
        ["UTM medium", lead.utm_medium],
        ["UTM campaign", lead.utm_campaign],
        ["UTM content", lead.utm_content],
        ["Ref", lead.ref],
        ["Đồng ý nhận liên hệ", lead.consent ? "Có" : "Không"],
        ["Trạng thái quà", lead.gift_status],
        ["Tạo lúc", formatDateTime(lead.created_at)],
        ["Cập nhật lúc", formatDateTime(lead.updated_at)],
        ["Phát quà lúc", formatDateTime(lead.redeemed_at)],
        ["Phát bởi", lead.redeemed_by]
      ].forEach(function (row) {
        list.appendChild(detailRow(row[0], row[1]));
      });

      var title = document.createElement("p");
      title.className = "h3";
      title.textContent = "Chi tiết lead";
      detailBox.appendChild(title);
      detailBox.appendChild(list);
    });
  }

  /* ------------------------------------------------------------- export CSV */

  function filenameFrom(response) {
    var header = response.headers.get("content-disposition") || "";
    var match = header.match(/filename="([^"]+)"/);
    return match ? match[1] : "vipphone-leads.csv";
  }

  function exportCsv() {
    var params = filterParams(1);
    params.delete("page");
    params.delete("page_size");

    setStatus("Đang xuất CSV…");
    showError("");

    callApi("/api/admin/leads.csv?" + params.toString(), { raw: true }).then(function (result) {
      if (!result.ok || !result.response) {
        setStatus("");
        showError(explainFailure(result, "Không xuất được CSV."));
        return;
      }

      return result.response.blob().then(function (blob) {
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = filenameFrom(result.response);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        var truncated = result.response.headers.get("X-VIPPHONE-CSV-Truncated") === "true";
        var rows = result.response.headers.get("X-VIPPHONE-CSV-Rows") || "?";
        setStatus(
          truncated
            ? "Đã xuất " + rows + " dòng — CHẠM TRẦN nên file KHÔNG đầy đủ. Thu hẹp bộ lọc rồi xuất lại."
            : "Đã xuất " + rows + " dòng theo đúng bộ lọc đang áp dụng."
        );
      });
    });
  }

  /* -------------------------------------------------------- danh mục iPhone */

  function renderModels(models) {
    modelRows.innerHTML = "";
    modelSelect.innerHTML = "";

    var all = document.createElement("option");
    all.value = "";
    all.textContent = "Tất cả";
    modelSelect.appendChild(all);

    if (!models.length) {
      var empty = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 6;
      td.textContent = "Danh mục đang trống.";
      empty.appendChild(td);
      modelRows.appendChild(empty);
      return;
    }

    models.forEach(function (model) {
      var option = document.createElement("option");
      option.value = model.model_code;
      option.textContent = model.display_name;
      modelSelect.appendChild(option);

      var tr = document.createElement("tr");
      tr.appendChild(cell(model.model_code));
      tr.appendChild(cell(model.display_name));
      tr.appendChild(cell(model.year));
      tr.appendChild(cell(model.sort_order));
      tr.appendChild(cell(model.active ? "Có" : "Không"));

      var actionCell = document.createElement("td");
      var button = document.createElement("button");
      button.type = "button";
      button.className = "secondary-btn small-btn";
      button.textContent = model.active ? "Tắt" : "Bật";
      button.setAttribute(
        "aria-label",
        (model.active ? "Tắt" : "Bật") + " model " + model.display_name
      );
      button.addEventListener("click", function () {
        patchModel(model.model_code, { active: !model.active }, button);
      });
      actionCell.appendChild(button);
      tr.appendChild(actionCell);

      modelRows.appendChild(tr);
    });
  }

  function loadModels() {
    return callApi("/api/admin/iphone-models").then(function (result) {
      if (!result.ok || !result.body) {
        showModelError(explainFailure(result, "Không tải được danh mục iPhone."));
        return;
      }
      showModelError("");
      state.catalogLoaded = true;
      renderModels(result.body);
    });
  }

  function patchModel(code, payload, button) {
    if (button) button.disabled = true;
    setModelStatus("Đang cập nhật " + code + "…");

    callApi("/api/admin/iphone-models/" + encodeURIComponent(code), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (result) {
      if (button) button.disabled = false;
      if (!result.ok) {
        setModelStatus("");
        showModelError(
          fieldErrorOf(result.body) || explainFailure(result, "Không cập nhật được model.")
        );
        return;
      }
      showModelError("");
      setModelStatus("Đã cập nhật " + result.body.display_name + ".");
      loadModels();
    });
  }

  function submitModel(event) {
    event.preventDefault();
    showModelError("");

    var codeInput = document.getElementById("mCode");
    var nameInput = document.getElementById("mName");
    var yearInput = document.getElementById("mYear");
    var sortInput = document.getElementById("mSort");
    var activeInput = document.getElementById("mActive");

    var payload = {
      model_code: String(codeInput.value || "").trim().toLowerCase(),
      display_name: String(nameInput.value || "").trim(),
      year: Number(yearInput.value),
      sort_order: sortInput.value === "" ? 0 : Number(sortInput.value),
      active: !!activeInput.checked
    };

    if (!payload.model_code) {
      showModelError("Nhập mã model (slug), ví dụ: iphone-17-pro.");
      return;
    }
    if (!payload.display_name) {
      showModelError("Nhập tên hiển thị, ví dụ: iPhone 17 Pro.");
      return;
    }
    if (!Number.isFinite(payload.year) || payload.year < 2007) {
      showModelError("Năm phải là số và từ 2007 trở lên.");
      return;
    }

    setModelStatus("Đang thêm model…");
    var submitBtn = document.getElementById("modelSubmit");
    if (submitBtn) submitBtn.disabled = true;

    callApi("/api/admin/iphone-models", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (result) {
      if (submitBtn) submitBtn.disabled = false;

      if (!result.ok) {
        setModelStatus("");
        showModelError(
          fieldErrorOf(result.body) || explainFailure(result, "Không thêm được model.")
        );
        return;
      }

      setModelStatus(
        "Đã thêm " + result.body.display_name + ". Landing sẽ thấy model này ngay, không cần sửa HTML."
      );
      modelForm.reset();
      document.getElementById("mSort").value = "0";
      document.getElementById("mActive").checked = true;
      loadModels();
    });
  }

  /* -------------------------------------------------------------- khởi động */

  filterForm.addEventListener("submit", function (event) {
    event.preventDefault();
    loadLeads(1);
  });

  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      filterForm.reset();
      document.getElementById("fPageSize").value = "50";
      detailBox.innerHTML = "";
      loadLeads(1);
    });
  }

  if (exportBtn) {
    exportBtn.addEventListener("click", exportCsv);
  }

  prevBtn.addEventListener("click", function () {
    if (state.page > 1) loadLeads(state.page - 1);
  });

  nextBtn.addEventListener("click", function () {
    var pageSize = state.pageSize || 50;
    var totalPages = Math.max(1, Math.ceil(state.total / pageSize));
    if (state.page < totalPages) loadLeads(state.page + 1);
  });

  if (modelForm) {
    modelForm.addEventListener("submit", submitModel);
  }

  if (keyInput) {
    try {
      var stored = sessionStorage.getItem(STAFF_KEY_STORAGE);
      if (stored) keyInput.value = stored;
    } catch (err) {
      /* chế độ riêng tư */
    }
  }

  if (readKey()) {
    loadLeads(1);
    if (modelForm) loadModels();
    if (keyInput) keyInput.focus();
  } else {
    // Không có khoá thì KHÔNG bắn request chắc chắn sẽ 401. Nói thẳng cần gì.
    setStatus("Nhập khoá truy cập nhân viên rồi bấm TÌM KIẾM.");
    if (modelForm) {
      modelRows.innerHTML = "";
      var hint = document.createElement("tr");
      var hintCell = document.createElement("td");
      hintCell.colSpan = 6;
      hintCell.textContent = "Nhập khoá truy cập nhân viên để tải danh mục.";
      hint.appendChild(hintCell);
      modelRows.appendChild(hint);
    }
    if (keyInput) keyInput.focus();
  }
})();
