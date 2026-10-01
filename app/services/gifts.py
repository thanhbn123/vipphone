"""Nghiệp vụ gift: tra cứu, che PII, sinh ảnh QR chuẩn."""

from __future__ import annotations

import io

import qrcode
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..giftcodes import normalize_gift_code
from ..models import Lead
from ..schemas import GiftLookupResponse


def find_lead_by_gift_code(db: Session, gift_code: str) -> Lead | None:
    """Tra cứu KHÔNG phân biệt hoa/thường."""
    normalized = normalize_gift_code(gift_code)
    if not normalized:
        return None
    stmt = select(Lead).where(Lead.gift_code == normalized)
    return db.execute(stmt).scalar_one_or_none()


def mask_phone(phone: str) -> str:
    """Che số điện thoại để nhân viên đối chiếu mà không lộ toàn bộ số.

    `0912345678` → `0912***678`
    """
    value = (phone or "").strip()
    if len(value) < 7:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 7)}{value[-3:]}"


def to_lookup_response(lead: Lead) -> GiftLookupResponse:
    """Chỉ trả trường TỐI THIỂU cần cho việc phát quà tại quầy."""
    return GiftLookupResponse(
        lead_id=lead.lead_id,
        gift_code=lead.gift_code,
        gift_status=lead.gift_status,
        full_name=lead.full_name,
        phone_masked=mask_phone(lead.phone),
        iphone_model=lead.iphone_model,
        iphone_year=lead.iphone_year,
        case_color=lead.case_color,
        created_at=lead.created_at,
        redeemed_at=lead.redeemed_at,
    )


def render_qr_png(payload_url: str) -> bytes:
    """Sinh ảnh QR CHUẨN (ISO/IEC 18004) từ URL công khai.

    Nội dung QR CHỈ gồm URL nhận quà + gift code. TUYỆT ĐỐI không nhúng
    tên, số điện thoại, công ty hay bất kỳ PII nào.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload_url)
    qr.make(fit=True)

    image = qr.make_image(fill_color="#111827", back_color="#ffffff")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def redeem_url_for(gift_code: str) -> str:
    return settings.redeem_url(normalize_gift_code(gift_code))
