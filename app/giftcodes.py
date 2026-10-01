"""Sinh và chuẩn hoá gift code.

Yêu cầu:
- ngẫu nhiên, đủ entropy
- KHÔNG tuần tự
- KHÔNG suy trực tiếp từ id trong database
- tra cứu KHÔNG phân biệt hoa/thường
- ràng buộc UNIQUE ở DB; đụng độ thì THỬ LẠI, không báo lỗi cho khách
- tiền tố năm lấy từ cấu hình, KHÔNG hard-code
"""

from __future__ import annotations

import re
import secrets

from .config import settings

#: Kiểm tra cấu trúc tổng quát (dùng khi chưa biết cấu hình độ dài).
GIFT_CODE_STRUCTURE_RE = re.compile(r"^VIP-\d{2}-[A-Z0-9]{4,12}$")

#: Kiểm tra ĐÚNG độ dài đang cấu hình. Độ dài cấu hình được nên regex không
#: được hard-code cứng 6 ký tự.
GIFT_CODE_RE = re.compile(rf"^VIP-\d{{2}}-[A-Z0-9]{{{settings.gift_code_length}}}$")


def normalize_gift_code(raw: str | None) -> str:
    """Chuẩn hoá để tra cứu: bỏ khoảng trắng, viết hoa."""
    if not raw:
        return ""
    return re.sub(r"\s+", "", str(raw)).upper()


def is_well_formed_gift_code(raw: str | None) -> bool:
    return bool(GIFT_CODE_RE.match(normalize_gift_code(raw)))


def generate_gift_code(*, year_prefix: str | None = None) -> str:
    """Sinh một gift code mới bằng CSPRNG.

    Entropy: `gift_code_alphabet` (32 ký tự) ^ `gift_code_length` (6)
    = 32^6 ≈ 1,07 * 10^9 tổ hợp. Đủ cho quy mô chương trình quà tặng và
    có thể tăng qua biến môi trường khi cần.
    """
    prefix = year_prefix if year_prefix is not None else settings.year_prefix
    body = "".join(
        secrets.choice(settings.gift_code_alphabet) for _ in range(settings.gift_code_length)
    )
    return f"VIP-{prefix}-{body}"
