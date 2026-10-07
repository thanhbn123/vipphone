/*!
 * VIP PHONE — trang chi tiết sản phẩm `/product/{slug}` (G14).
 *
 * Slug lấy từ đường dẫn trình duyệt, rồi tra `/api/products/{slug}`. Slug không
 * tồn tại (hoặc sản phẩm đã tắt) ⇒ máy chủ trả 404 ⇒ trang hiện thông báo, KHÔNG
 * hiện hàng giả.
 *
 * KHÔNG bịa số lượng tồn kho: hệ thống chưa có sổ kho, nên chỉ có "Còn hàng" /
 * "Hết hàng" theo `availability` do máy chủ trả về.
 */
"use strict";

(function () {
  var util = window.VPUtil;
  var config = window.VIPPHONE_CONFIG || {};

  var errorBox = document.getElementById("productError");
  var detailBox = document.getElementById("productDetail");
  var categoryBox = document.getElementById("productCategory");
  var titleBox = document.getElementById("productTitle");
  var availabilityBox = document.getElementById("productAvailability");
  var bodyBox = document.getElementById("productBody");
  var aboutBox = document.getElementById("aboutShop");

  if (!errorBox || !detailBox || !bodyBox) return;

  function apiBase() {
    return config.apiBase || "";
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
    detailBox.hidden = true;
    if (aboutBox) aboutBox.hidden = false;
  }

  /** Tiền hiển thị: dùng CHUNG `assets/js/money.js` với `/shop` — xem tệp đó. */
  var formatMoney = window.VPMoney.formatMoney;

  function slugFromPath() {
    var parts = window.location.pathname.split("/").filter(function (part) {
      return part.length > 0;
    });
    if (parts.length < 2 || parts[0] !== "product") return "";
    return decodeURIComponent(parts[1]);
  }

  function compatibilityLine(variant) {
    if (!variant.compatibility || !variant.compatibility.length) {
      return "Chưa khai báo máy tương thích";
    }
    return variant.compatibility.map(function (c) {
      return c.device_model_code + " (" + c.compatibility_type + ")";
    }).join(" · ");
  }

  function skuBlock(variant) {
    var parts = [];
    parts.push('<li class="sku-item">');
    parts.push('<span class="sku-name">' + util.escapeHtml(variant.variant_name) + "</span>");
    if (variant.color) {
      parts.push('<span class="sku-color">' + util.escapeHtml(variant.color) + "</span>");
    }
    parts.push('<span class="sku-meta">Mã: ' + util.escapeHtml(variant.sku) + "</span>");
    parts.push('<span class="sku-price">' + util.escapeHtml(formatMoney(variant.sale_price, variant.currency)));
    if (variant.compare_at_price) {
      parts.push(' <s class="price-compare">' +
        util.escapeHtml(formatMoney(variant.compare_at_price, variant.currency)) + "</s>");
    }
    parts.push("</span>");
    parts.push('<span class="sku-compat">Dùng cho: ' + util.escapeHtml(compatibilityLine(variant)) + "</span>");
    parts.push("</li>");
    return parts.join("");
  }

  function render(product) {
    if (categoryBox) {
      categoryBox.textContent = product.category ? product.category.name : "Chưa phân nhóm";
    }
    titleBox.textContent = product.name;
    availabilityBox.textContent = product.availability === "IN_STOCK" ? "Còn hàng" : "Hết hàng";
    availabilityBox.className = product.availability === "IN_STOCK"
      ? "status ok" : "status warn";

    var parts = [];
    if (product.brand) {
      parts.push('<p class="product-brand">Thương hiệu: ' + util.escapeHtml(product.brand) + "</p>");
    }
    if (product.description) {
      parts.push('<p class="product-description">' + util.escapeHtml(product.description) + "</p>");
    }

    parts.push('<h2 class="h3">Phiên bản đang bán</h2>');
    if (!product.variants.length) {
      parts.push('<p class="status warn">Sản phẩm hiện không có phiên bản nào đang bán.</p>');
    } else {
      parts.push('<ul class="sku-list detail-list">');
      parts.push(product.variants.map(skuBlock).join(""));
      parts.push("</ul>");
    }

    parts.push('<p class="field-hint">Hệ thống chưa có sổ kho nên không hiển thị số lượng. ' +
      "Tình trạng chỉ là Còn hàng hoặc Hết hàng.</p>");
    parts.push('<p class="admin-actions">' +
      '<a class="primary-btn" href="/">ĐỂ LẠI THÔNG TIN ĐỂ ĐƯỢC TƯ VẤN</a>' +
      '<a class="secondary-btn" href="/shop">XEM PHỤ KIỆN KHÁC</a></p>');

    bodyBox.innerHTML = parts.join("");
    detailBox.hidden = false;
    errorBox.hidden = true;
    if (aboutBox) aboutBox.hidden = true;
    document.title = "VIP PHONE — " + product.name;
  }

  var slug = slugFromPath();
  if (!slug) {
    showError("Đường dẫn không hợp lệ.");
    return;
  }

  fetch(apiBase() + "/api/products/" + encodeURIComponent(slug), {
    headers: { Accept: "application/json" }
  })
    .then(function (response) {
      if (response.status === 404) {
        throw new Error("Không tìm thấy sản phẩm này.");
      }
      if (!response.ok) {
        return response.json().catch(function () { return null; }).then(function (body) {
          var message = body && body.error ? body.error.message : "Không tải được sản phẩm.";
          throw new Error(message);
        });
      }
      return response.json();
    })
    .then(render)
    .catch(function (error) {
      showError(error && error.message ? error.message : "Không tải được sản phẩm.");
    });
})();
