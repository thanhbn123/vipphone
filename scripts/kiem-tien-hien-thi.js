#!/usr/bin/env node
/*!
 * Chốt CI — TIỀN HIỂN THỊ PHẢI KHỚP TIỀN ĐÃ LƯU (G14, V8).
 *
 * VÌ SAO CÓ TỆP NÀY: bản `formatMoney` cũ dùng `Number(value)` +
 * `new Intl.NumberFormat("vi-VN")`, nên `"250000.10"` in ra `250.000,1 đ` — MẤT
 * chữ số 0 cuối, tức là hiển thị một mức giá khác mức giá đã lưu. Khách nhìn thấy
 * con số đó. Không có test nào bắt được, vì bộ test chỉ đo tầng API.
 *
 * Tệp này `require()` ĐÚNG tệp đang phục vụ khách (`assets/js/money.js`), không
 * chép lại logic. Nếu ai đó đưa `Number` trở lại, chốt này ĐỎ.
 *
 * Chạy:  node scripts/kiem-tien-hien-thi.js
 */
"use strict";

const path = require("path");

const MONEY_PATH = path.join(__dirname, "..", "assets", "js", "money.js");
const money = require(MONEY_PATH);

/** [đầu vào, loại tiền, chuỗi PHẢI hiện ra] */
const CASES = [
  // Ca sinh ra bản vá: mất số 0 cuối ⇒ hiển thị lệch giá đã lưu.
  ["250000.10", "VND", "250.000,10 đ"],
  ["250000.05", "VND", "250.000,05 đ"],
  ["123456.78", "VND", "123.456,78 đ"],
  // Giá tròn vẫn phải đủ 2 chữ số thập phân, không được rút thành "250.000 đ".
  ["250000.00", "VND", "250.000,00 đ"],
  ["0.00", "VND", "0,00 đ"],
  ["7.5", "VND", "7,50 đ"],
  // Nhóm nghìn ở nhiều mức, gồm mốc 4 chữ số (không được ra "1.0000,00").
  ["1000.00", "VND", "1.000,00 đ"],
  ["999.99", "VND", "999,99 đ"],
  ["1000000000.00", "VND", "1.000.000.000,00 đ"],
  // Số 0 vô nghĩa ở đầu không được lọt ra màn hình.
  ["007.00", "VND", "7,00 đ"],
  // Nhiều hơn 2 chữ số thập phân: làm tròn nửa lên, KHÔNG cắt cụt.
  ["1234.567", "VND", "1.234,57 đ"],
  ["1234.564", "VND", "1.234,56 đ"],
  ["9.999", "VND", "10,00 đ"],
  ["99.995", "VND", "100,00 đ"],
  // Tiền âm (chiết khấu/điều chỉnh): dấu phải đứng TRƯỚC phần nhóm nghìn.
  ["-250000.10", "VND", "-250.000,10 đ"],
  // Loại tiền khác VND in mã ISO, không bịa ký hiệu.
  ["12.34", "USD", "12,34 USD"],
  ["12.34", "", "12,34"],
];

/** Giá trị không phải chuỗi thập phân: trả nguyên văn, KHÔNG đoán thành 0. */
const RAW_CASES = [
  ["", "VND", ""],
  [null, "VND", ""],
  ["khong-phai-so", "VND", "khong-phai-so đ"],
  ["1e5", "VND", "1e5 đ"],
  ["1,5", "VND", "1,5 đ"],
];

const failures = [];

for (const [value, currency, expected] of CASES.concat(RAW_CASES)) {
  let actual;
  try {
    actual = money.formatMoney(value, currency);
  } catch (error) {
    failures.push(
      `  ${JSON.stringify(value)} (${currency || "không tiền tệ"}) → NÉM LỖI: ${error.message}`
    );
    continue;
  }
  const mark = actual === expected ? "OK  " : "ĐỎ  ";
  if (actual !== expected) {
    failures.push(
      `  ${JSON.stringify(value)} (${currency || "không tiền tệ"}) → ` +
        `nhận ${JSON.stringify(actual)}, phải là ${JSON.stringify(expected)}`
    );
  }
  console.log(`${mark} ${JSON.stringify(value)} (${currency || "-"}) → ${actual}`);
}

// Chốt cấu trúc: nguồn tiền KHÔNG được quay lại `Number(` / `parseFloat` / `Intl`.
// Phải BỎ CHÚ THÍCH trước khi quét — chính tài liệu trong tệp có nhắc tên những hàm
// này (để giải thích vì sao cấm), và quét thô sẽ báo động giả rồi chốt thành vô dụng.
const rawSource = require("fs").readFileSync(MONEY_PATH, "utf8");
const code = rawSource
  .replace(/\/\*[\s\S]*?\*\//g, "") // khối /* ... */
  .replace(/(^|[^:])\/\/.*$/gm, "$1"); // dòng // ... (tránh cắt nhầm "https://")
for (const forbidden of ["Number(", "parseFloat", "parseInt", "Intl."]) {
  if (code.includes(forbidden)) {
    failures.push(
      `  assets/js/money.js chứa ${forbidden} — tiền KHÔNG được đi qua số thực.`
    );
  }
}

if (failures.length > 0) {
  console.error("\nTIỀN HIỂN THỊ SAI — chốt CI ĐỎ:");
  console.error(failures.join("\n"));
  process.exit(1);
}

console.log(
  `\nTIỀN HIỂN THỊ OK — ${CASES.length + RAW_CASES.length} ca, ` +
    "định dạng từ CHUỖI thập phân, không dùng Number/Intl."
);
