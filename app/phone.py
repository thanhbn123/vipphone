"""Chuẩn hoá và kiểm tra số điện thoại Việt Nam.

Bản này là NGUỒN CHÂN LÝ. `assets/js/util.js` ở frontend phải cho ra
CÙNG kết quả — lệch nhau là lỗi (xem docs/lead-schema.md).
"""

from __future__ import annotations

import re

#: Di động Việt Nam: 0 + [3|5|7|8|9] + 8 chữ số = 10 chữ số.
VN_MOBILE_RE = re.compile(r"^0[35789]\d{8}$")

#: Độ dài tối đa cho phép của đầu vào thô, chặn payload rác.
MAX_RAW_LENGTH = 32

#: Độ dài tối đa của kết quả sau chuẩn hoá. Số di động Việt Nam là 10 chữ số;
#: để 12 cho dư địa, nhưng KHÔNG để lọt chuỗi dài vào cột `phone` (String(16)).
MAX_NORMALIZED_LENGTH = 12


def normalize_phone(raw: str | None) -> str:
    """Chuẩn hoá về dạng canonical `0xxxxxxxxx`.

    `+84 912 345 678`, `84912345678`, `0912.345.678` → `0912345678`

    Vì sao bắt buộc: chính sách chống trùng dựa trên số đã chuẩn hoá. Nếu
    `+849…` và `09…` cho ra hai giá trị khác nhau thì CÙNG MỘT KHÁCH sẽ
    nhận hai gift code.
    """
    if not raw:
        return ""

    text = str(raw).strip()[:MAX_RAW_LENGTH]

    # Giữ chữ số, và dấu '+' chỉ khi nó đứng đầu.
    digits = re.sub(r"[^\d+]", "", text)
    if digits.startswith("+"):
        digits = "+" + digits[1:].replace("+", "")
    else:
        digits = digits.replace("+", "")

    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    elif digits.startswith("84") and len(digits) >= 11:
        digits = "0" + digits[2:]

    return re.sub(r"\D", "", digits)[:MAX_NORMALIZED_LENGTH]


def is_valid_vn_mobile(raw: str | None) -> bool:
    return bool(VN_MOBILE_RE.match(normalize_phone(raw)))


def is_valid_canonical_phone(value: str) -> bool:
    """Kiểm tra một giá trị ĐÃ chuẩn hoá (dùng cho dữ liệu đọc từ DB/import)."""
    return bool(VN_MOBILE_RE.match(value or ""))
