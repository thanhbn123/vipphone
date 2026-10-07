/*!
 * VIP PHONE — trang cửa hàng `/shop` (G14).
 *
 * Ba luật của file này:
 * 1. KHÔNG hard-code sản phẩm, nhóm hàng hay dòng máy. Mọi thứ đến từ API
 *    (`/api/products`, `/api/catalog/categories`, `/api/catalog/iphone-models`).
 * 2. KHÔNG bịa số lượng tồn kho. Hệ thống chưa có sổ kho, nên chỉ có hai nhãn
 *    "Còn hàng" / "Hết hàng", suy từ `availability` do máy chủ trả về.
 * 3. Mọi nội dung chèn vào DOM đi qua `VPUtil.escapeHtml` — không ngoại lệ.
 */
"use strict";

(function () {
  var util = window.VPUtil;
  var config = window.VIPPHONE_CONFIG || {};

  var form = document.getElementById("shopFilters");
  var categorySelect = document.getElementById("filterCategory");
  var deviceSelect = document.getElementById("filterDevice");
  var keywordInput = document.getElementById("filterKeyword");
  var resetBtn = document.getElementById("filterReset");
  var countBox = document.getElementById("shopCount");
  var errorBox = document.getElementById("shopError");
  var listBox = document.getElementById("productList");
  var pager = document.getElementById("pager");
  var prevBtn = document.getElementById("prevPage");
  var nextBtn = document.getElementById("nextPage");
  var pageInfo = document.getElementById("pageInfo");

  if (!form || !listBox) return;

  var PAGE_SIZE = 24;
  var state = { page: 1, total: 0 };

  function apiBase() {
    return config.apiBase || "";
  }

  function showError(message) {
    if (!errorBox) return;
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  function clearError() {
    if (errorBox) errorBox.hidden = true;
  }

  /* --------------------------------------------------------------- tiện ích */

  // Tiền hiển thị đi qua `assets/js/money.js` — MỘT bản duy nhất, và bản đó định
  // dạng từ CHUỖI thập phân, KHÔNG qua `Number`. Xem đầu tệp đó để biết vì sao.
  var formatMoney = window.VPMoney.formatMoney;

  function availabilityLabel(code) {
    return code === "IN_STOCK" ? "Còn hàng" : "Hết hàng";
  }

  function availabilityClass(code) {
    return code === "IN_STOCK" ? "badge badge-in" : "badge badge-out";
  }

  /* ------------------------------------------------------- nạp bộ lọc */

  function fillSelect(select, items, valueOf, labelOf) {
    if (!select) return;
    items.forEach(function (item) {
      var option = document.createElement("option");
      option.value = valueOf(item);
      option.textContent = labelOf(item);
      select.appendChild(option);
    });
  }

  function loadFilters() {
    return Promise.all([
      fetch(apiBase() + "/api/catalog/categories", { headers: { Accept: "application/json" } })
        .then(function (r) { return r.ok ? r.json() : []; })
        .catch(function () { return []; }),
      fetch(apiBase() + "/api/catalog/iphone-models", { headers: { Accept: "application/json" } })
        .then(function (r) { return r.ok ? r.json() : []; })
        .catch(function () { return []; })
    ]).then(function (results) {
      fillSelect(categorySelect, results[0], function (c) { return c.code; },
        function (c) { return c.name; });
      fillSelect(deviceSelect, results[1], function (m) { return m.model_code; },
        function (m) { return m.display_name; });
    });
  }

  /* ----------------------------------------------------------- đọc/ghi URL */

  function readQuery() {
    var params = new URLSearchParams(window.location.search);
    return {
      category: params.get("category") || "",
      device_model: params.get("device_model") || "",
      q: params.get("q") || "",
      page: Math.max(1, parseInt(params.get("page") || "1", 10) || 1)
    };
  }

  function writeQuery(extra) {
    var params = new URLSearchParams();
    if (categorySelect && categorySelect.value) params.set("category", categorySelect.value);
    if (deviceSelect && deviceSelect.value) params.set("device_model", deviceSelect.value);
    if (keywordInput && keywordInput.value.trim()) params.set("q", keywordInput.value.trim());
    if (extra && extra.page && extra.page > 1) params.set("page", String(extra.page));
    var query = params.toString();
    var url = window.location.pathname + (query ? "?" + query : "");
    window.history.replaceState(null, "", url);
    return query;
  }

  function applyQueryToForm(query) {
    if (categorySelect) categorySelect.value = query.category;
    if (deviceSelect) deviceSelect.value = query.device_model;
    if (keywordInput) keywordInput.value = query.q;
  }

  /* ------------------------------------------------------------- vẽ giao diện */

  function compatibilityText(variant) {
    if (!variant.compatibility || !variant.compatibility.length) return "Chưa khai báo máy tương thích";
    return variant.compatibility.map(function (c) {
      return c.device_model_code;
    }).join(", ");
  }

  function variantHtml(variant) {
    var parts = [];
    parts.push('<li class="sku-item">');
    parts.push('<span class="sku-name">' + util.escapeHtml(variant.variant_name) + "</span>");
    if (variant.color) {
      parts.push('<span class="sku-color">' + util.escapeHtml(variant.color) + "</span>");
    }
    parts.push('<span class="sku-price">' + util.escapeHtml(formatMoney(variant.sale_price, variant.currency)));
    if (variant.compare_at_price) {
      parts.push(' <s class="price-compare">' +
        util.escapeHtml(formatMoney(variant.compare_at_price, variant.currency)) + "</s>");
    }
    parts.push("</span>");
    parts.push('<span class="sku-compat">' + util.escapeHtml(compatibilityText(variant)) + "</span>");
    parts.push("</li>");
    return parts.join("");
  }

  function productHtml(product) {
    var href = "/product/" + encodeURIComponent(product.slug);
    var categoryName = product.category ? product.category.name : "Chưa phân nhóm";
    var price = product.variants.length ? product.variants[0].sale_price : null;
    var currency = product.variants.length ? product.variants[0].currency : "VND";

    var parts = [];
    parts.push('<article class="product-card">');
    // Ảnh CHÍNH (máy chủ đặt ảnh chính đứng đầu). Ảnh luôn cùng origin (/media/...).
    var image = product.images && product.images.length ? product.images[0] : null;
    if (image) {
      parts.push('<a class="product-thumb" href="' + util.escapeHtml(href) + '">' +
        '<img src="' + util.escapeHtml(image.url) + '" alt="' + util.escapeHtml(image.alt_text) +
        '" width="' + parseInt(image.width, 10) + '" height="' + parseInt(image.height, 10) +
        '" loading="lazy" decoding="async"></a>');
    }
    parts.push('<p class="product-category">' + util.escapeHtml(categoryName) + "</p>");
    parts.push('<h3 class="product-name"><a href="' + util.escapeHtml(href) + '">' +
      util.escapeHtml(product.name) + "</a></h3>");
    parts.push('<p class="' + availabilityClass(product.availability) + '">' +
      util.escapeHtml(availabilityLabel(product.availability)) + "</p>");
    if (price === null) {
      parts.push('<p class="product-price">Chưa có SKU đang bán</p>');
    } else {
      parts.push('<p class="product-price">' + util.escapeHtml(formatMoney(price, currency)) + "</p>");
    }
    parts.push('<ul class="sku-list">');
    parts.push(product.variants.map(variantHtml).join(""));
    parts.push("</ul>");
    parts.push('<p class="admin-actions"><a class="secondary-btn" href="' +
      util.escapeHtml(href) + '">XEM CHI TIẾT</a></p>');
    parts.push("</article>");
    return parts.join("");
  }

  function render(payload) {
    if (!payload.items.length) {
      listBox.innerHTML = '<p class="status warn">Không có sản phẩm nào khớp bộ lọc.</p>';
    } else {
      listBox.innerHTML = payload.items.map(productHtml).join("");
    }
    if (countBox) {
      countBox.textContent = payload.total === 0
        ? "Không có sản phẩm nào."
        : "Tìm thấy " + payload.total + " sản phẩm — trang " + payload.page + ".";
    }
    renderPager(payload);
  }

  function renderPager(payload) {
    if (!pager) return;
    var lastPage = Math.max(1, Math.ceil(payload.total / (payload.page_size || PAGE_SIZE)));
    if (payload.total === 0 || lastPage <= 1) {
      pager.hidden = true;
      return;
    }
    pager.hidden = false;
    if (pageInfo) pageInfo.textContent = "Trang " + payload.page + " / " + lastPage;
    if (prevBtn) prevBtn.disabled = payload.page <= 1;
    if (nextBtn) nextBtn.disabled = payload.page >= lastPage;
  }

  /* ------------------------------------------------------------- tải dữ liệu */

  function load() {
    var query = writeQuery({ page: state.page });
    var url = apiBase() + "/api/products?" + query + (query ? "&" : "") +
      "page=" + state.page + "&page_size=" + PAGE_SIZE;

    if (countBox) countBox.textContent = "Đang tải…";
    clearError();

    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          return response.json().catch(function () { return null; }).then(function (body) {
            var message = body && body.error ? body.error.message : "Không tải được danh sách.";
            throw new Error(message);
          });
        }
        return response.json();
      })
      .then(function (payload) {
        state.total = payload.total;
        render(payload);
      })
      .catch(function (error) {
        showError(error && error.message ? error.message : "Không tải được danh sách sản phẩm.");
        listBox.innerHTML = "";
        if (countBox) countBox.textContent = "";
        if (pager) pager.hidden = true;
      });
  }

  /* ------------------------------------------------------------- sự kiện */

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    state.page = 1;
    load();
  });

  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      if (categorySelect) categorySelect.value = "";
      if (deviceSelect) deviceSelect.value = "";
      if (keywordInput) keywordInput.value = "";
      state.page = 1;
      load();
    });
  }

  if (prevBtn) {
    prevBtn.addEventListener("click", function () {
      state.page = Math.max(1, state.page - 1);
      load();
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", function () {
      state.page = state.page + 1;
      load();
    });
  }

  var initial = readQuery();
  state.page = initial.page;

  loadFilters().then(function () {
    applyQueryToForm(initial);
    return load();
  });
})();
