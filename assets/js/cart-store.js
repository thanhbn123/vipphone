/*!
 * VIP PHONE — G16: kho giỏ hàng phía trình duyệt (dùng chung cho mọi trang).
 *
 * Trình duyệt CHỈ giữ `cart_id` + `cart_token` (token sở hữu, không phải PII)
 * trong localStorage. Mọi GIÁ và TỔNG đều do máy chủ trả về — trang không tự
 * tính tiền, không gửi giá lên.
 *
 * Giỏ mất (404: token sai/giỏ bị dọn) hoặc đã đặt (409 CART_NOT_ACTIVE) ⇒ quên giỏ
 * cũ và tạo giỏ mới một lần, không lặp vô hạn.
 */
"use strict";

(function () {
  var KEY = "vipphone_cart_v1";
  var config = window.VIPPHONE_CONFIG || {};

  function apiBase() {
    return config.apiBase || "";
  }

  function read() {
    try {
      var raw = localStorage.getItem(KEY);
      var parsed = raw ? JSON.parse(raw) : null;
      return parsed && parsed.cart_id && parsed.cart_token ? parsed : null;
    } catch (err) {
      return null;
    }
  }

  function write(value) {
    try {
      if (value) localStorage.setItem(KEY, JSON.stringify(value));
      else localStorage.removeItem(KEY);
    } catch (err) {
      /* chế độ riêng tư: giỏ chỉ sống trong trang hiện tại */
    }
  }

  function request(method, path, body, token) {
    var headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers["X-Cart-Token"] = token;
    return fetch(apiBase() + path, {
      method: method,
      headers: headers,
      body: body === undefined ? undefined : JSON.stringify(body)
    }).then(function (response) {
      return response.json().catch(function () { return null; }).then(function (data) {
        return { status: response.status, ok: response.ok, data: data };
      });
    });
  }

  function errorOf(result, fallback) {
    var err = new Error(
      result.data && result.data.error ? result.data.error.message : fallback
    );
    err.status = result.status;
    err.code = result.data && result.data.error ? result.data.error.code : null;
    err.fields = result.data && result.data.error ? result.data.error.fields : null;
    return err;
  }

  function createCart() {
    return request("POST", "/api/cart").then(function (result) {
      if (!result.ok) throw errorOf(result, "Không tạo được giỏ hàng.");
      var stored = { cart_id: result.data.cart_id, cart_token: result.data.cart_token };
      write(stored);
      return stored;
    });
  }

  function ensure() {
    var stored = read();
    return stored ? Promise.resolve(stored) : createCart();
  }

  function isStale(result) {
    return result.status === 404 &&
      result.data && result.data.error && result.data.error.code === "CART_NOT_FOUND" ||
      result.status === 409 &&
      result.data && result.data.error && result.data.error.code === "CART_NOT_ACTIVE";
  }

  /** Gọi một thao tác trên giỏ; giỏ cũ hỏng thì làm lại ĐÚNG MỘT lần trên giỏ mới. */
  function withCart(op, retried) {
    return ensure().then(function (stored) {
      return op(stored).then(function (result) {
        if (isStale(result) && !retried) {
          write(null);
          return withCart(op, true);
        }
        if (!result.ok) throw errorOf(result, "Không cập nhật được giỏ hàng.");
        return result.data;
      });
    });
  }

  function get() {
    var stored = read();
    if (!stored) return Promise.resolve(null);
    return request("GET", "/api/cart/" + stored.cart_id, undefined, stored.cart_token)
      .then(function (result) {
        if (result.status === 404) {
          write(null);
          return null;
        }
        if (!result.ok) throw errorOf(result, "Không tải được giỏ hàng.");
        return result.data;
      });
  }

  function add(sku, quantity) {
    return withCart(function (s) {
      return request("POST", "/api/cart/" + s.cart_id + "/items",
        { sku: sku, quantity: quantity || 1 }, s.cart_token);
    });
  }

  function update(sku, quantity) {
    var s = read();
    if (!s) return Promise.reject(new Error("Chưa có giỏ hàng."));
    return request("PATCH", "/api/cart/" + s.cart_id + "/items/" + encodeURIComponent(sku),
      { quantity: quantity }, s.cart_token).then(function (result) {
      if (!result.ok) throw errorOf(result, "Không cập nhật được số lượng.");
      return result.data;
    });
  }

  function remove(sku) {
    var s = read();
    if (!s) return Promise.reject(new Error("Chưa có giỏ hàng."));
    return request("DELETE", "/api/cart/" + s.cart_id + "/items/" + encodeURIComponent(sku),
      undefined, s.cart_token).then(function (result) {
      if (!result.ok) throw errorOf(result, "Không xoá được sản phẩm.");
      return result.data;
    });
  }

  window.VPCart = {
    read: read,
    forget: function () { write(null); },
    get: get,
    add: add,
    update: update,
    remove: remove,
    request: request,
    errorOf: errorOf
  };
})();
