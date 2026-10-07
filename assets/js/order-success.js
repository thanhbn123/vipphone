/*!
 * VIP PHONE — G16: trang `/order/success`. Đọc đơn bằng token của CHÍNH chủ đơn.
 */
"use strict";

(function () {
  var ORDER_KEY = "vipphone_last_order_v1";
  var formatMoney = window.VPMoney.formatMoney;

  var STATUS_TEXT = {
    PENDING_PAYMENT: "Đơn đang chờ xác nhận / thanh toán.",
    CONFIRMED: "Đơn đã được xác nhận.",
    PROCESSING: "Đơn đang được chuẩn bị.",
    SHIPPED: "Đơn đang được giao.",
    COMPLETED: "Đơn đã hoàn tất.",
    CANCELLED: "Đơn đã huỷ."
  };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function showError(message) {
    var box = document.getElementById("orderError");
    box.textContent = message;
    box.hidden = false;
  }

  var stored = null;
  try {
    stored = JSON.parse(sessionStorage.getItem(ORDER_KEY) || "null");
  } catch (err) {
    stored = null;
  }
  if (!stored || !stored.order_id || !stored.token) {
    showError("Không tìm thấy thông tin đơn trong phiên này. Vui lòng liên hệ VIP PHONE nếu cần hỗ trợ.");
    return;
  }

  fetch((window.VIPPHONE_CONFIG.apiBase || "") + "/api/orders/" + encodeURIComponent(stored.order_id), {
    headers: { Accept: "application/json", "X-Order-Token": stored.token }
  })
    .then(function (response) {
      if (!response.ok) throw new Error("Không tải được đơn hàng.");
      return response.json();
    })
    .then(function (order) {
      document.getElementById("orderNumber").textContent = order.order_number;
      document.getElementById("orderStatus").textContent =
        STATUS_TEXT[order.status] || order.status;
      var list = document.getElementById("orderLines");
      order.items.forEach(function (item) {
        var li = el("li", "cart-line");
        li.appendChild(el("span", "cart-line-name",
          item.quantity + " × " + item.product_name + " — " + item.variant_name));
        li.appendChild(el("span", "cart-line-total", formatMoney(item.line_total, order.currency)));
        list.appendChild(li);
      });
      document.getElementById("orderSubtotal").textContent = formatMoney(order.subtotal, order.currency);
      document.getElementById("orderShipping").textContent = formatMoney(order.shipping_fee, order.currency);
      document.getElementById("orderGrand").textContent = formatMoney(order.grand_total, order.currency);
      document.getElementById("orderRecipient").textContent =
        order.recipient_name + " · " + order.phone_masked + " · " + order.province;
      document.getElementById("orderBox").hidden = false;
    })
    .catch(function (error) { showError(error.message); });
})();
