"""API gift: tra cứu cho nhân viên + ảnh QR công khai."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import NotFound
from ..giftcodes import is_well_formed_gift_code, normalize_gift_code
from ..schemas import GiftLookupResponse
from ..security import require_staff
from ..services.gifts import find_lead_by_gift_code, render_qr_png, to_lookup_response

router = APIRouter(prefix="/api/gifts", tags=["gifts"])


@router.get(
    "/{gift_code}",
    response_model=GiftLookupResponse,
    summary="Tra cứu gift cho nhân viên (cần xác thực)",
)
def lookup_gift(
    gift_code: str,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> GiftLookupResponse:
    """Trả thông tin TỐI THIỂU. Không trả số điện thoại đầy đủ, không trả UTM."""
    del actor  # chỉ dùng để chặn truy cập

    code = normalize_gift_code(gift_code)
    if not is_well_formed_gift_code(code):
        raise NotFound("GIFT_NOT_FOUND", "Mã quà không đúng định dạng.")

    lead = find_lead_by_gift_code(db, code)
    if lead is None:
        raise NotFound("GIFT_NOT_FOUND", "Không tìm thấy mã quà.")

    return to_lookup_response(lead)


@router.get(
    "/{gift_code}/qr.png",
    summary="Ảnh QR chuẩn cho gift code (công khai, KHÔNG chứa PII)",
    response_class=Response,
)
def gift_qr_png(gift_code: str, db: Session = Depends(get_db)) -> Response:
    """Sinh QR chuẩn ISO/IEC 18004.

    Nội dung QR CHỈ có URL công khai dạng `<PUBLIC_BASE_URL>/redeem?code=...`.
    KHÔNG nhúng tên, số điện thoại, công ty hay bất kỳ PII nào.

    Route này công khai vì QR không chứa PII và bản thân gift code đã là
    thông tin khách đang giữ. Route KHÔNG trả về tên khách hay số điện thoại.
    """
    code = normalize_gift_code(gift_code)
    if not is_well_formed_gift_code(code):
        raise NotFound("GIFT_NOT_FOUND", "Mã quà không đúng định dạng.")

    lead = find_lead_by_gift_code(db, code)
    if lead is None:
        raise NotFound("GIFT_NOT_FOUND", "Không tìm thấy mã quà.")

    from ..services.gifts import redeem_url_for

    png = render_qr_png(redeem_url_for(lead.gift_code))

    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="vip-phone-{lead.gift_code}.png"',
        },
    )
