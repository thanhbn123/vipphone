/*!
 * VIP PHONE — G16: trang `/checkout`.
 *
 * - KHÔNG gửi giá. Chỉ gửi `expected_total` = tổng máy chủ đã báo, để máy chủ
 *   phát hiện giá đổi (409 PRICE_CHANGED) — máy chủ vẫn tự tính lại từ đầu.
 * - `Idempotency-Key` sinh MỘT lần cho giỏ này và giữ trong sessionStorage ⇒
 *   bấm đúp / mạng chập chờn / tải lại trang KHÔNG tạo đơn thứ hai.
 * - Tracking không PII: `vipphone_checkout_start`, `vipphone_order_created`
 *   (chỉ mã đơn, giá trị, số món — không tên, SĐT, email, địa chỉ).
 */
"use strict";

(function () {
  var ORDER_KEY = "vipphone_last_order_v1";
  var formatMoney = window.VPMoney.formatMoney;
  var track = window.VPTrack ? window.VPTrack.track : function () {};

  var form = document.getElementById("checkoutForm");
  var errorBox = document.getElementById("checkoutError");
  var submit = document.getElementById("placeOrder");
  var currentCart = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  function randomKey() {
    var bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    return Array.prototype.map.call(bytes, function (b) {
      return ("0" + b.toString(16)).slice(-2);
    }).join("");
  }

  function idempotencyKey(cartId) {
    var storageKey = "vipphone_idem_" + cartId;
    try {
      var existing = sessionStorage.getItem(storageKey);
      if (existing) return existing;
      var fresh = randomKey();
      sessionStorage.setItem(storageKey, fresh);
      return fresh;
    } catch (err) {
      return randomKey();
    }
  }

  function renderSummary(cart) {
    var list = document.getElementById("summaryLines");
    list.textContent = "";
    cart.items.forEach(function (item) {
      var li = el("li", "cart-line");
      li.appendChild(el("span", "cart-line-name",
        item.quantity + " × " + item.product_name + " — " + item.variant_name));
      li.appendChild(el("span", "cart-line-total", formatMoney(item.line_total, item.currency)));
      list.appendChild(li);
    });
    document.getElementById("sumSubtotal").textContent = formatMoney(cart.subtotal, cart.currency);
    document.getElementById("sumShipping").textContent = formatMoney(cart.shipping_fee, cart.currency);
    document.getElementById("sumGrand").textContent = formatMoney(cart.grand_total, cart.currency);
  }

  function clearFieldErrors() {
    Array.prototype.forEach.call(form.querySelectorAll("[data-error-for]"), function (node) {
      node.textContent = "";
    });
  }

  function showFieldErrors(fields) {
    if (!fields) return;
    Object.keys(fields).forEach(function (name) {
      var node = form.querySelector('[data-error-for="' + name + '"]');
      if (node) node.textContent = fields[name];
    });
  }

  function value(name) {
    return String(form.elements[name].value || "").trim();
  }

  function payload(cart) {
    var name = value("full_name");
    var phone = value("phone");
    return {
      cart_id: cart.cart_id,
      customer: { full_name: name, phone: phone, email: value("email") || null },
      shipping: {
        recipient_name: name,
        phone: phone,
        address_line: value("address_line"),
        ward: value("ward") || null,
        district: value("district") || null,
        province: value("province")
      },
      customer_note: value("customer_note") || null,
      expected_total: cart.grand_total
    };
  }

  function onSubmit(event) {
    event.preventDefault();
    if (!currentCart) return;
    clearFieldErrors();
    errorBox.hidden = true;
    submit.disabled = true;

    var stored = window.VPCart.read();
    fetch((window.VIPPHONE_CONFIG.apiBase || "") + "/api/checkout", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Cart-Token": stored.cart_token,
        "Idempotency-Key": idempotencyKey(currentCart.cart_id)
      },
      body: JSON.stringify(payload(currentCart))
    })
      .then(function (response) {
        return response.json().catch(function () { return null; }).then(function (data) {
          if (response.status === 201) return data;
          var error = data && data.error ? data.error : {};
          if (error.code === "PRICE_CHANGED") {
            return window.VPCart.get().then(function (cart) {
              currentCart = cart;
              renderSummary(cart);
              throw new Error("Giá vừa thay đổi. Vui lòng xem lại tổng tiền rồi bấm đặt hàng lần nữa.");
            });
          }
          showFieldErrors(error.fields);
          throw new Error(error.message || "Không đặt được hàng. Vui lòng thử lại.");
        });
      })
      .then(function (order) {
        try {
          sessionStorage.setItem(ORDER_KEY, JSON.stringify({
            order_id: order.order_id,
            token: stored.cart_token
          }));
        } catch (err) { /* trang thành công sẽ báo không tìm thấy */ }
        track("vipphone_order_created", {
          order_number: order.order_number,
          value: order.grand_total,
          currency: order.currency,
          item_count: order.items.reduce(function (n, i) { return n + i.quantity; }, 0)
        });
        window.VPCart.forget();
        window.location.assign("/order/success");
      })
      .catch(function (error) {
        showError(error.message);
        submit.disabled = false;
      });
  }

  window.VPCart.get().then(function (cart) {
    if (!cart || !cart.items.length) {
      showError("Giỏ hàng đang trống.");
      form.hidden = true;
      return;
    }
    currentCart = cart;
    renderSummary(cart);
    track("vipphone_checkout_start", {
      value: cart.grand_total,
      currency: cart.currency,
      item_count: cart.item_count
    });
    form.addEventListener("submit", onSubmit);
  }).catch(function (e) { showError(e.message); });
})();
