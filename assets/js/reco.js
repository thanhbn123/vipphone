/*!
 * VIP PHONE — G15: gợi ý phụ kiện trên trang thành công.
 *
 * Nguồn dữ liệu: `/api/recommendations?device_model=<MÃ máy>`. Đầu vào DUY NHẤT
 * là mã máy — không gửi tên, số điện thoại, email hay địa chỉ đi đâu cả.
 *
 * Tracking (dataLayer, KHÔNG PII): chỉ `product_id`, `sku`, `category`,
 * `device_model_code`, `source_surface`, `rank`.
 *
 * Vẽ bằng DOM + `textContent`, không `innerHTML` với dữ liệu từ API.
 */
"use strict";

(function () {
  var RESULT_KEY = "vipphone_last_gift_v1";
  var SURFACE = "post_gift_success";
  var MODEL_CODE = /^[a-z0-9-]{1,64}$/;

  var section = document.getElementById("recoSection");
  var list = document.getElementById("recoList");
  var deviceLabel = document.getElementById("recoDevice");
  if (!section || !list) return;

  var track = window.VPTrack ? window.VPTrack.track : function () {};
  var formatMoney = window.VPMoney.formatMoney;

  function readResult() {
    try {
      var raw = sessionStorage.getItem(RESULT_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (err) {
      return null;
    }
  }

  function apiBase() {
    return (window.VIPPHONE_CONFIG && window.VIPPHONE_CONFIG.apiBase) || "";
  }

  function shopHref(modelCode, category) {
    var params = new URLSearchParams();
    if (category) params.set("category", category);
    params.set("device_model", modelCode);
    return "/shop?" + params.toString();
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function card(item, modelCode) {
    var product = item.product;
    var variant = product.variants[0];
    var href = "/product/" + encodeURIComponent(product.slug);

    var article = el("article", "product-card reco-item");
    article.setAttribute("data-reco-rank", String(item.rank));
    article.appendChild(el("p", "product-category", product.category ? product.category.name : ""));

    var title = el("h3", "product-name");
    var link = el("a", null, product.name);
    link.href = href;
    title.appendChild(link);
    article.appendChild(title);

    if (variant) {
      article.appendChild(el("p", "product-price", formatMoney(variant.sale_price, variant.currency)));
    }

    var button = el("a", "secondary-btn", "XEM CHI TIẾT");
    button.href = href;
    var actions = el("p", "admin-actions");
    actions.appendChild(button);
    article.appendChild(actions);

    function onClick() {
      track("vipphone_recommendation_click", {
        product_id: product.product_id,
        sku: variant ? variant.sku : null,
        category: item.category_code,
        device_model_code: modelCode,
        source_surface: SURFACE,
        rank: item.rank
      });
    }
    link.addEventListener("click", onClick);
    button.addEventListener("click", onClick);
    return article;
  }

  function render(payload, modelCode, deviceName) {
    if (deviceLabel) deviceLabel.textContent = deviceName || modelCode;

    document.getElementById("recoCtaGlass").href = shopHref(modelCode, "SCREEN_PROTECTOR");
    document.getElementById("recoCtaCharge").href = shopHref(modelCode, "CHARGER");
    document.getElementById("recoCtaAll").href = shopHref(modelCode, "");

    list.textContent = "";
    payload.items.forEach(function (item) {
      list.appendChild(card(item, modelCode));
    });
    section.hidden = false;

    track("vipphone_recommendation_view", {
      device_model_code: modelCode,
      source_surface: SURFACE,
      item_count: payload.items.length,
      product_ids: payload.items.map(function (i) { return i.product.product_id; })
    });
  }

  function init() {
    var result = readResult();
    if (!result || !result.model_code || !MODEL_CODE.test(result.model_code)) return;
    var modelCode = result.model_code;

    fetch(apiBase() + "/api/recommendations?device_model=" + encodeURIComponent(modelCode), {
      headers: { Accept: "application/json" }
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (payload) {
        // Không có gì để gợi ý ⇒ KHÔNG hiện khung rỗng. Gợi ý là phần phụ.
        if (!payload || !payload.items || !payload.items.length) return;
        render(payload, modelCode, result.iphone_model);
      })
      .catch(function () {
        /* Gợi ý lỗi không được làm hỏng trang mã quà. */
      });
  }

  init();
})();
