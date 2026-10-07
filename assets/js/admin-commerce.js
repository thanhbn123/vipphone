/*!
 * VIP PHONE — trang quản trị bán hàng: đơn hàng, thanh toán, kho, giá & ảnh, nguồn khách.
 *
 * Mọi dữ liệu đến từ `/api/admin/*` kèm khoá nhân viên (sessionStorage, CHỈ phiên
 * của tab — dùng chung khoá với trang quản trị lead). Vẽ bằng DOM + `textContent`,
 * không chèn HTML từ dữ liệu. Tiền hiển thị qua `window.VPMoney` (từ CHUỖI thập phân).
 */
"use strict";

(function () {
  var STAFF_KEY_STORAGE = "vipphone_staff_key_v1";
  var config = window.VIPPHONE_CONFIG || {};
  var money = window.VPMoney.formatMoney;

  var keyInput = document.getElementById("staffKey");
  var errorBox = document.getElementById("adminError");
  var statusBox = document.getElementById("adminStatus");

  /* ------------------------------------------------------------ tiện ích */
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function td(text) {
    return el("td", null, text === null || text === undefined ? "—" : String(text));
  }

  function button(label, onClick, kind) {
    var b = el("button", kind || "secondary-btn", label);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  function when(value) {
    if (!value) return "—";
    var d = new Date(value);
    return isNaN(d.getTime()) ? "—" : d.toLocaleString("vi-VN");
  }

  function readKey() {
    if (keyInput && keyInput.value.trim()) {
      try { sessionStorage.setItem(STAFF_KEY_STORAGE, keyInput.value.trim()); } catch (e) { /* riêng tư */ }
      return keyInput.value.trim();
    }
    try { return sessionStorage.getItem(STAFF_KEY_STORAGE) || ""; } catch (e) { return ""; }
  }

  function showError(message) {
    errorBox.textContent = message || "";
    errorBox.hidden = !message;
  }

  function status(message) {
    statusBox.textContent = message || "";
  }

  /** Gọi API quản trị. Trả `{ok, status, body}` — không ném lỗi ra ngoài. */
  function api(path, opts) {
    var options = opts || {};
    var headers = options.headers || {};
    var key = readKey();
    if (key) headers["X-Staff-Key"] = key;
    if (options.json !== undefined) headers["Content-Type"] = "application/json";
    return fetch((config.apiBase || "") + path, {
      method: options.method || "GET",
      headers: headers,
      body: options.json !== undefined ? JSON.stringify(options.json) : options.body
    }).then(function (response) {
      return response.json().catch(function () { return null; }).then(function (body) {
        if (!response.ok) {
          var message = response.status === 401
            ? "Khoá nhân viên sai hoặc thiếu."
            : body && body.error ? body.error.message : "Lỗi " + response.status;
          showError(message);
        } else {
          showError("");
        }
        return { ok: response.ok, status: response.status, body: body };
      });
    }).catch(function () {
      showError("Không kết nối được máy chủ.");
      return { ok: false, status: 0, body: null };
    });
  }

  /* ------------------------------------------------------------ chuyển mục */
  var loaders = {};
  function openTab(name) {
    Array.prototype.forEach.call(document.querySelectorAll("[data-panel]"), function (panel) {
      panel.hidden = panel.getAttribute("data-panel") !== name;
    });
    if (loaders[name]) loaders[name]();
  }
  Array.prototype.forEach.call(document.querySelectorAll("[data-tab]"), function (b) {
    b.addEventListener("click", function () { openTab(b.getAttribute("data-tab")); });
  });

  /* ------------------------------------------------------------ ĐƠN HÀNG */
  var orderRows = document.getElementById("orderRows");
  var orderDetail = document.getElementById("orderDetail");

  function loadOrders() {
    var params = new URLSearchParams();
    var s = document.getElementById("oStatus").value;
    var p = document.getElementById("oPayment").value;
    var q = document.getElementById("oQuery").value.trim();
    if (s) params.set("status", s);
    if (p) params.set("payment_status", p);
    if (q) params.set("q", q);
    return api("/api/admin/orders?" + params.toString()).then(function (r) {
      orderRows.textContent = "";
      if (!r.ok) return;
      status("Tìm thấy " + r.body.total + " đơn.");
      r.body.items.forEach(function (o) {
        var tr = el("tr");
        tr.setAttribute("data-order", o.order_number);
        [o.order_number, o.customer_name + " · " + o.phone_masked, o.status, o.payment_status,
          money(o.grand_total, o.currency), when(o.created_at)].forEach(function (v) { tr.appendChild(td(v)); });
        var cell = el("td");
        cell.appendChild(button("Xem", function () { showOrder(o.order_id); }));
        tr.appendChild(cell);
        orderRows.appendChild(tr);
      });
    });
  }

  function kv(parent, label, value) {
    var row = el("p", "detail-row");
    row.appendChild(el("strong", null, label + ": "));
    row.appendChild(document.createTextNode(value === null || value === undefined || value === "" ? "—" : String(value)));
    parent.appendChild(row);
  }

  function attributionText(a) {
    if (!a) return "—";
    var parts = ["source", "campaign", "ref", "utm_source", "utm_medium", "utm_campaign", "utm_content"]
      .filter(function (k) { return a[k]; })
      .map(function (k) { return k + "=" + a[k]; });
    return parts.length ? parts.join(" · ") : "(trực tiếp)";
  }

  function showOrder(orderId) {
    Promise.all([
      api("/api/admin/orders/" + orderId),
      api("/api/admin/orders/" + orderId + "/payments")
    ]).then(function (results) {
      var detail = results[0];
      var payments = results[1];
      if (!detail.ok) return;
      var o = detail.body;
      orderDetail.textContent = "";
      orderDetail.hidden = false;
      orderDetail.appendChild(el("h3", "h3", "Đơn " + o.order_number));
      kv(orderDetail, "Trạng thái", o.status);
      kv(orderDetail, "Thanh toán", o.payment_status);
      kv(orderDetail, "Khách", o.customer_name + " · " + o.phone_masked);
      kv(orderDetail, "Giao tới", [o.shipping.recipient_name, o.shipping.phone, o.shipping.address_line,
        o.shipping.ward, o.shipping.district, o.shipping.province].filter(Boolean).join(", "));
      kv(orderDetail, "Ghi chú", o.customer_note);
      kv(orderDetail, "Nguồn của đơn", attributionText(o.attribution));
      kv(orderDetail, "Nguồn đầu tiên của khách", attributionText(o.customer_first_touch));

      var items = el("ul", "detail-list");
      o.items_detail.forEach(function (i) {
        items.appendChild(el("li", null, i.quantity + " × " + i.product_name + " — " + i.variant_name +
          " (" + i.sku + ") = " + money(i.line_total, o.currency)));
      });
      orderDetail.appendChild(items);
      kv(orderDetail, "Tạm tính", money(o.subtotal, o.currency));
      kv(orderDetail, "Phí giao", money(o.shipping_fee, o.currency));
      kv(orderDetail, "Tổng", money(o.grand_total, o.currency));

      var actions = el("p", "admin-actions");
      o.allowed_transitions.forEach(function (to) {
        actions.appendChild(button("→ " + to, function () {
          var reason = window.prompt("Lý do (không bắt buộc):", "") || null;
          api("/api/admin/orders/" + orderId + "/status", {
            method: "POST", json: { to_status: to, reason: reason }
          }).then(function (r) { if (r.ok) { showOrder(orderId); loadOrders(); } });
        }));
      });
      orderDetail.appendChild(actions);

      orderDetail.appendChild(el("h4", null, "Khoản thanh toán"));
      (payments.ok ? payments.body : []).forEach(function (p) {
        var box = el("div", "detail-box");
        box.setAttribute("data-payment", p.method);
        kv(box, p.method, p.status + " · " + money(p.amount, p.currency) +
          (p.confirmed_by ? " · xác nhận bởi " + p.confirmed_by : ""));
        var acts = el("p", "admin-actions");
        p.allowed_actions.forEach(function (action) {
          acts.appendChild(button(action.toUpperCase(), function () {
            var note = window.prompt("Ghi chú (không bắt buộc):", "") || null;
            api("/api/admin/payments/" + p.payment_id + "/" + action, {
              method: "POST", json: { note: note }
            }).then(function (r) { if (r.ok) { showOrder(orderId); loadOrders(); } });
          }));
        });
        box.appendChild(acts);
        var ev = el("ul", "detail-list");
        p.events.forEach(function (e) {
          ev.appendChild(el("li", null, when(e.created_at) + " · " + e.event_type + " · " +
            (e.from_status || "∅") + " → " + (e.to_status || "∅") + " · " + e.outcome + " · " + e.actor));
        });
        box.appendChild(ev);
        orderDetail.appendChild(box);
      });

      orderDetail.appendChild(el("h4", null, "Lịch sử trạng thái"));
      var hist = el("ul", "detail-list");
      o.events.forEach(function (e) {
        hist.appendChild(el("li", null, when(e.created_at) + " · " + e.field + ": " +
          (e.from_value || "∅") + " → " + e.to_value + " · " + e.actor + (e.reason ? " · " + e.reason : "")));
      });
      orderDetail.appendChild(hist);
    });
  }

  document.getElementById("orderFilter").addEventListener("submit", function (e) {
    e.preventDefault();
    loadOrders();
  });
  loaders.orders = loadOrders;

  /* ------------------------------------------------------------ KHO */
  var invRows = document.getElementById("invRows");
  var invDetail = document.getElementById("invDetail");
  var currentSku = null;

  function loadInventory() {
    var low = document.getElementById("invLow").checked ? "&low_stock_below=5" : "";
    return api("/api/admin/inventory?tracked_only=true" + low).then(function (r) {
      invRows.textContent = "";
      if (!r.ok) return;
      r.body.forEach(function (b) {
        var tr = el("tr");
        tr.setAttribute("data-sku", b.sku);
        [b.sku, b.product_name + " — " + b.variant_name, b.quantity_on_hand, b.quantity_reserved,
          b.quantity_available].forEach(function (v) { tr.appendChild(td(v)); });
        var cell = el("td");
        cell.appendChild(button("Sổ kho", function () { showInventory(b.sku); }));
        tr.appendChild(cell);
        invRows.appendChild(tr);
      });
    });
  }

  function showInventory(sku) {
    currentSku = sku;
    return api("/api/admin/inventory/" + encodeURIComponent(sku)).then(function (r) {
      if (!r.ok) return;
      var b = r.body.balance;
      document.getElementById("invTitle").textContent =
        b.sku + " — tồn " + b.quantity_on_hand + ", giữ " + b.quantity_reserved + ", bán được " + b.quantity_available;
      var tbody = document.getElementById("invMoves");
      tbody.textContent = "";
      r.body.movements.forEach(function (m) {
        var tr = el("tr");
        [m.id, m.movement_type, m.delta_on_hand, m.delta_reserved, m.order_number, m.actor, m.reason,
          when(m.created_at)].forEach(function (v) { tr.appendChild(td(v)); });
        tbody.appendChild(tr);
      });
      invDetail.hidden = false;
    });
  }

  document.getElementById("invForm").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!currentSku) return;
    api("/api/admin/inventory/" + encodeURIComponent(currentSku) + "/movements", {
      method: "POST",
      json: {
        movement_type: document.getElementById("invType").value,
        quantity: parseInt(document.getElementById("invQty").value, 10),
        reason: document.getElementById("invReason").value.trim() || null
      }
    }).then(function (r) {
      if (r.ok) { status("Đã ghi biến động kho."); showInventory(currentSku); loadInventory(); }
    });
  });
  document.getElementById("invReload").addEventListener("click", loadInventory);
  document.getElementById("invLow").addEventListener("change", loadInventory);
  loaders.inventory = loadInventory;

  /* ------------------------------------------------------------ SẢN PHẨM */
  var prodRows = document.getElementById("prodRows");
  var prodDetail = document.getElementById("prodDetail");
  var currentProduct = null;

  function loadProducts() {
    return api("/api/admin/products?page_size=100").then(function (r) {
      prodRows.textContent = "";
      if (!r.ok) return;
      r.body.items.forEach(function (p) {
        var tr = el("tr");
        tr.setAttribute("data-product", p.slug);
        var first = p.variants[0];
        [p.name, p.variants.map(function (v) { return v.sku; }).join(", "),
          first ? money(first.sale_price, first.currency) : "—", p.images.length].forEach(function (v) {
          tr.appendChild(td(v));
        });
        var cell = el("td");
        cell.appendChild(button("Sửa", function () { showProduct(p); }));
        tr.appendChild(cell);
        prodRows.appendChild(tr);
      });
    });
  }

  function refreshProduct(productId) {
    return api("/api/admin/products/" + productId).then(function (r) {
      if (r.ok) showProduct(r.body);
    });
  }

  function loadPriceHistory(sku) {
    return api("/api/admin/variants/" + encodeURIComponent(sku) + "/price-history").then(function (r) {
      var tbody = document.getElementById("priceRows");
      tbody.textContent = "";
      if (!r.ok) return;
      r.body.forEach(function (h) {
        var tr = el("tr");
        [h.old_price === null ? "—" : money(h.old_price, h.currency), money(h.new_price, h.currency),
          h.changed_by, when(h.changed_at), h.reason].forEach(function (v) { tr.appendChild(td(v)); });
        tbody.appendChild(tr);
      });
    });
  }

  function showProduct(p) {
    currentProduct = p;
    prodDetail.hidden = false;
    document.getElementById("prodTitle").textContent = p.name;
    var select = document.getElementById("priceSku");
    select.textContent = "";
    p.variants.forEach(function (v) {
      var opt = el("option", null, v.sku + " — " + money(v.sale_price, v.currency));
      opt.value = v.sku;
      select.appendChild(opt);
    });
    if (p.variants.length) loadPriceHistory(p.variants[0].sku);

    var list = document.getElementById("imageList");
    list.textContent = "";
    p.images.forEach(function (img) {
      var fig = el("figure", "admin-image");
      var image = document.createElement("img");
      image.src = img.url;
      image.alt = img.alt_text;
      image.width = 160;
      image.height = Math.round(160 * img.height / img.width);
      fig.appendChild(image);
      fig.appendChild(el("figcaption", null, (img.is_primary ? "★ ẢNH CHÍNH · " : "") + img.alt_text));
      var acts = el("p", "admin-actions");
      if (!img.is_primary) {
        acts.appendChild(button("Đặt làm ảnh chính", function () {
          api("/api/admin/products/" + p.product_id + "/images/" + img.image_id, {
            method: "PATCH", json: { is_primary: true }
          }).then(function (r) { if (r.ok) showProduct(r.body); });
        }));
      }
      acts.appendChild(button("Xoá", function () {
        if (!window.confirm("Xoá ảnh này?")) return;
        api("/api/admin/products/" + p.product_id + "/images/" + img.image_id, { method: "DELETE" })
          .then(function (r) { if (r.ok) showProduct(r.body); });
      }));
      fig.appendChild(acts);
      list.appendChild(fig);
    });
  }

  document.getElementById("priceSku").addEventListener("change", function (e) {
    loadPriceHistory(e.target.value);
  });

  document.getElementById("priceForm").addEventListener("submit", function (e) {
    e.preventDefault();
    var sku = document.getElementById("priceSku").value;
    api("/api/admin/variants/" + encodeURIComponent(sku), {
      method: "PATCH",
      json: {
        sale_price: document.getElementById("priceNew").value.trim(),
        price_change_reason: document.getElementById("priceReason").value.trim() || null
      }
    }).then(function (r) {
      if (!r.ok) return;
      status("Đã đổi giá " + sku + ".");
      showProduct(r.body);
      document.getElementById("priceSku").value = sku;
      loadPriceHistory(sku);
      loadProducts();
    });
  });

  document.getElementById("imageForm").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!currentProduct) return;
    var file = document.getElementById("imageFile").files[0];
    var alt = document.getElementById("imageAlt").value.trim();
    if (!file || !alt) return;
    // Gửi BYTE ẢNH thô — máy chủ kiểm magic bytes và mã hoá lại (bỏ EXIF).
    api("/api/admin/products/" + currentProduct.product_id + "/images?alt_text=" + encodeURIComponent(alt), {
      method: "POST",
      headers: { "Content-Type": file.type },
      body: file
    }).then(function (r) {
      if (r.ok) { status("Đã tải ảnh lên."); showProduct(r.body); loadProducts(); }
    });
  });
  loaders.products = loadProducts;

  /* ------------------------------------------------------------ BÁO CÁO */
  function loadReport() {
    var params = new URLSearchParams({
      model: document.getElementById("repModel").value,
      dimension: document.getElementById("repDim").value
    });
    return api("/api/admin/reports/attribution?" + params.toString()).then(function (r) {
      var tbody = document.getElementById("repRows");
      tbody.textContent = "";
      if (!r.ok) return;
      r.body.rows.forEach(function (row) {
        var tr = el("tr");
        [row.key === null ? "(trực tiếp)" : row.key, row.customers, row.orders,
          money(row.revenue, "VND"), money(row.paid_revenue, "VND")].forEach(function (v) { tr.appendChild(td(v)); });
        tbody.appendChild(tr);
      });
    });
  }
  document.getElementById("repForm").addEventListener("submit", function (e) {
    e.preventDefault();
    loadReport();
  });
  loaders.report = loadReport;

  /* ------------------------------------------------------------ khởi động */
  try {
    var saved = sessionStorage.getItem(STAFF_KEY_STORAGE);
    if (saved && keyInput) keyInput.value = saved;
  } catch (e) { /* riêng tư */ }
  if (readKey()) loadOrders();
})();
