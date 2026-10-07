/*!
 * VIP PHONE — ĐỊNH DẠNG TIỀN ĐỂ HIỂN THỊ (G14).
 *
 * MỘT bản duy nhất, dùng chung cho `/shop` và `/product/{slug}`. Trước đây mỗi
 * trang có một bản `formatMoney` chép tay; hai bản thì sẽ lệch nhau, và bản lệch
 * là bản nói dối khách về giá (xem CLAUDE.md §12.2 "lọc một chỗ, không lọc hai chỗ").
 *
 * ---------------------------------------------------------------------------
 * LUẬT CỦA FILE NÀY: **KHÔNG BAO GIỜ đổi tiền sang `Number`.**
 * ---------------------------------------------------------------------------
 *
 * Máy chủ trả giá là CHUỖI thập phân chính xác (`"250000.10"`, `"250000.00"` —
 * cột DB là `Numeric(12,2)`, schema Pydantic là `Decimal`). `Number("250000.10")`
 * ra `250000.1`, và `Intl.NumberFormat("vi-VN")` in ra `250.000,1` — MẤT chữ số 0
 * cuối, tức là hiển thị một mức giá KHÁC mức giá đã lưu. Đó không phải lỗi thẩm
 * mỹ: khách nhìn thấy số tiền, và số đó phải đúng.
 *
 * Vì vậy ở đây cắt chuỗi, đệm chữ số và chèn dấu phân cách bằng tay. Không `Intl`,
 * không `Number`, không sai số nhị phân. Đúng 2 chữ số thập phân, luôn luôn.
 *
 * Tệp này chạy được ở CẢ hai nơi:
 *   - trình duyệt: gán `window.VPMoney`
 *   - node:        `require("./assets/js/money.js")` — nhờ đó test đo ĐÚNG mã đang chạy
 *                  thật, không phải một bản chép lại trong bộ test.
 */
"use strict";

(function (root) {
  /** Ký hiệu tiền. `VND` hiện ra là `đ`; các loại khác in mã ISO nguyên văn. */
  function currencySuffix(currency) {
    if (currency === "VND") return "đ";
    return currency || "";
  }

  /** Chuỗi thập phân hợp lệ: `-?\d+(\.\d+)?`. Không chấp nhận `1e5`, `NaN`, `1,5`. */
  var DECIMAL_PATTERN = /^-?\d+(?:\.\d+)?$/;

  /** Cộng 1 vào một chuỗi chữ số (dùng khi làm tròn bị nhớ). `"199"` → `"200"`. */
  function incrementDigits(digits) {
    var out = "";
    var carry = 1;
    for (var i = digits.length - 1; i >= 0; i -= 1) {
      var digit = digits.charCodeAt(i) - 48 + carry;
      if (digit > 9) {
        digit = 0;
        carry = 1;
      } else {
        carry = 0;
      }
      out = String(digit) + out;
    }
    return carry ? "1" + out : out;
  }

  /**
   * Định dạng một giá trị tiền để IN RA.
   *
   * @param {string|number} value Chuỗi thập phân từ API (`"250000.10"`).
   * @param {string} [currency] Mã ISO 3 chữ, `"VND"` → hậu tố `đ`.
   * @returns {string} ví dụ `"250.000,10 đ"`.
   *
   * Giá trị KHÔNG phải chuỗi thập phân (rỗng, `null`, rác) thì trả NGUYÊN VĂN kèm
   * hậu tố — cố ý KHÔNG đoán, KHÔNG in ra "0 đ". Một mức giá sai mà im lặng còn tệ
   * hơn một mức giá lộ ra là sai.
   */
  function formatMoney(value, currency) {
    var suffix = currencySuffix(currency);
    var raw = value === null || value === undefined ? "" : String(value).trim();
    // Không có gì để hiện thì hiện RỖNG — không in trơ ra "đ".
    if (raw === "") return "";
    if (!DECIMAL_PATTERN.test(raw)) {
      return suffix ? raw + " " + suffix : raw;
    }

    var negative = raw.charAt(0) === "-";
    if (negative) raw = raw.slice(1);

    var parts = raw.split(".");
    // Bỏ số 0 vô nghĩa ở đầu (`"007"` → `"7"`), nhưng luôn giữ ít nhất một chữ số.
    var integer = parts[0].replace(/^0+(?=\d)/, "");
    var fraction = parts.length > 1 ? parts[1] : "";

    // Chuẩn hoá về ĐÚNG 2 chữ số thập phân. `digits` là toàn bộ chữ số của
    // `giá trị × 10^len(fraction)`; `keep` là số chữ số ứng với `giá trị × 100`.
    var keep = integer.length + 2;
    var digits = integer + fraction;
    if (digits.length <= keep) {
      digits += "00".slice(0, keep - digits.length);
    } else {
      var roundUp = digits.charAt(keep) >= "5"; // nửa lên, xét bằng CHUỖI
      digits = digits.slice(0, keep);
      if (roundUp) digits = incrementDigits(digits);
    }

    integer = digits.slice(0, digits.length - 2);
    fraction = digits.slice(digits.length - 2);
    var grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".");

    // `-0,00` là số 0 trần: đừng hiện dấu trừ vô nghĩa.
    var sign = negative && !(integer === "0" && fraction === "00") ? "-" : "";
    var text = sign + grouped + "," + fraction;
    return suffix ? text + " " + suffix : text;
  }

  var api = {
    formatMoney: formatMoney,
    currencySuffix: currencySuffix,
  };

  root.VPMoney = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
