/*!
 * VIP PHONE — G16: trang `/cart`. Hiển thị giỏ do MÁY CHỦ tính tiền.
 * Tracking không PII: `vipphone_remove_from_cart` (sku, quantity).
 */
"use strict";

(function () {
  var formatMoney = window.VPMoney.formatMoney;
  var track = window.VPTrack ? window.VPTrack.track : function () {};

  var lines = document.getElementById("cartLines");
  var errorBox = document.getElementById("cartError");
  var emptyBox = document.getElementById("cartEmpty");
  var totals = document.getElementById("cartTotals");
  var toCheckout = document.getElementById("toCheckout");

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

  function line(item) {
    var li = el("li", "cart-line" + (item.available ? "" : " unavailable"));
    li.setAttribute("data-sku", item.sku);
    li.appendChild(el("span", "cart-line-name",
      item.product_name + " — " + item.variant_name + (item.available ? "" : " (ngừng bán)")));
    li.appendChild(el("span", "cart-line-price", formatMoney(item.unit_price, item.currency)));

    var qty = document.createElement("input");
    qty.type = "number";
    qty.min = "1";
    qty.max = "99";
    qty.value = String(item.quantity);
    qty.setAttribute("aria-label", "Số lượng " + item.product_name);
    qty.addEventListener("change", function () {
      var value = parseInt(qty.value, 10);
      if (!(value >= 1 && value <= 99)) {
        qty.value = String(item.quantity);
        return;
      }
      window.VPCart.update(item.sku, value).then(render).catch(function (e) { showError(e.message); });
    });
    li.appendChild(qty);

    li.appendChild(el("span", "cart-line-total", formatMoney(item.line_total, item.currency)));

    var removeBtn = el("button", "secondary-btn", "Xoá");
    removeBtn.type = "button";
    removeBtn.addEventListener("click", function () {
      window.VPCart.remove(item.sku).then(function (cart) {
        track("vipphone_remove_from_cart", { sku: item.sku, quantity: item.quantity });
        render(cart);
      }).catch(function (e) { showError(e.message); });
    });
    li.appendChild(removeBtn);
    return li;
  }

  function render(cart) {
    lines.textContent = "";
    errorBox.hidden = true;
    if (!cart || !cart.items.length) {
      emptyBox.hidden = false;
      totals.hidden = true;
      toCheckout.hidden = true;
      return;
    }
    emptyBox.hidden = true;
    cart.items.forEach(function (item) { lines.appendChild(line(item)); });
    document.getElementById("cartSubtotal").textContent = formatMoney(cart.subtotal, cart.currency);
    document.getElementById("cartShipping").textContent = formatMoney(cart.shipping_fee, cart.currency);
    document.getElementById("cartGrand").textContent = formatMoney(cart.grand_total, cart.currency);
    totals.hidden = false;
    var blocked = cart.items.some(function (i) { return !i.available; });
    toCheckout.hidden = blocked || cart.item_count === 0;
    if (blocked) showError("Có sản phẩm đã ngừng bán. Vui lòng xoá khỏi giỏ để đặt hàng.");
  }

  window.VPCart.get().then(render).catch(function (e) { showError(e.message); });
})();
