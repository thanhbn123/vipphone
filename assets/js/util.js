/*!
 * VIP PHONE — tiện ích dùng chung (escape, chuẩn hoá số điện thoại, gift code)
 *
 * Các hàm ở đây là bản DUY NHẤT trong frontend. Từ G02, server là nguồn
 * chân lý cho chuẩn hoá/validation; bản này chỉ để phản hồi nhanh cho người
 * dùng và phải cho ra CÙNG kết quả với server. Lệch nhau = lỗi.
 */
"use strict";

(function () {
  /**
   * Escape HTML. Dùng cho MỌI chỗ nội dung người dùng được chèn vào DOM.
   * Không có ngoại lệ.
   */
  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value).replace(
      /[&<>"']/g,
      function (c) {
        return {
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;"
        }[c];
      }
    );
  }

  /**
   * Chuẩn hoá số điện thoại Việt Nam về dạng canonical `0xxxxxxxxx`.
   *
   * Vì sao phải canonical: chính sách chống trùng dựa trên số điện thoại đã
   * chuẩn hoá. Nếu `+84912345678` và `0912345678` cho ra hai giá trị khác
   * nhau thì cùng một khách sẽ nhận hai gift code.
   */
  function normalizePhone(raw) {
    var digits = String(raw === null || raw === undefined ? "" : raw)
      .replace(/[^\d+]/g, "")
      .replace(/\+/g, function (ch, offset) { return offset === 0 ? "+" : ""; });

    if (digits.indexOf("+84") === 0) {
      digits = "0" + digits.slice(3);
    } else if (digits.indexOf("84") === 0 && digits.length >= 11) {
      digits = "0" + digits.slice(2);
    }

    return digits.replace(/\D/g, "");
  }

  /** Số di động Việt Nam hợp lệ: 0 + [3|5|7|8|9] + 8 chữ số = 10 chữ số. */
  function isValidVnMobile(raw) {
    return /^0[35789]\d{8}$/.test(normalizePhone(raw));
  }

  /** Hiển thị số điện thoại canonical cho dễ đọc: 0912 345 678 */
  function formatPhone(raw) {
    var p = normalizePhone(raw);
    if (!/^0\d{9}$/.test(p)) return p;
    return p.slice(0, 4) + " " + p.slice(4, 7) + " " + p.slice(7);
  }

  /**
   * Chuẩn hoá gift code để tra cứu: bỏ khoảng trắng, viết hoa.
   * Tra cứu gift code KHÔNG phân biệt hoa/thường.
   */
  function normalizeGiftCode(raw) {
    return String(raw === null || raw === undefined ? "" : raw)
      .replace(/\s+/g, "")
      .toUpperCase();
  }

  var GIFT_CODE_PATTERN = /^VIP-\d{2}-[A-Z0-9]{6}$/;

  function isWellFormedGiftCode(raw) {
    return GIFT_CODE_PATTERN.test(normalizeGiftCode(raw));
  }

  /**
   * Tiền tố năm của gift code, KHÔNG hard-code.
   * Cấu hình được qua `window.VIPPHONE_GIFT_YEAR_PREFIX` (đặt trong HTML hoặc
   * server inject). Mặc định suy từ năm hiện tại.
   */
  function giftYearPrefix() {
    var configured = window.VIPPHONE_GIFT_YEAR_PREFIX;
    if (configured !== undefined && configured !== null && configured !== "") {
      return String(configured).padStart(2, "0").slice(-2);
    }
    return String(new Date().getFullYear() % 100).padStart(2, "0");
  }

  window.VPUtil = {
    escapeHtml: escapeHtml,
    normalizePhone: normalizePhone,
    isValidVnMobile: isValidVnMobile,
    formatPhone: formatPhone,
    normalizeGiftCode: normalizeGiftCode,
    isWellFormedGiftCode: isWellFormedGiftCode,
    giftYearPrefix: giftYearPrefix,
    GIFT_CODE_PATTERN: GIFT_CODE_PATTERN
  };
})();
