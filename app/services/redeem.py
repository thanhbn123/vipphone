"""Nghiệp vụ phát quà (redeem).

YÊU CẦU KHẮC NGHIỆT:
- chỉ cho redeem MỘT lần
- giao dịch nguyên tử: hai nhân viên trên hai máy KHÔNG được phát quà hai lần
- idempotent rõ ràng: đã REDEEMED thì trả `already_redeemed = true`
- audit ghi CÙNG transaction với thay đổi trạng thái
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_event
from ..errors import ApiError, NotFound
from ..giftcodes import is_well_formed_gift_code, normalize_gift_code
from ..models import AuditEventType, GiftStatus, Lead

logger = logging.getLogger("vipphone.redeem")

#: Chỉ những trạng thái này mới được chuyển sang REDEEMED.
REDEEMABLE_STATUSES = frozenset(
    {GiftStatus.NEW.value, GiftStatus.CONFIRMED.value, GiftStatus.READY.value}
)


@dataclass(slots=True)
class RedeemResult:
    lead: Lead
    already_redeemed: bool


def locked_lead_query(gift_code: str):
    """Câu truy vấn lấy lead kèm KHOÁ HÀNG.

    Tách riêng để test kiểm được **câu SQL thật sự dùng** (phải có `FOR UPDATE`),
    chứ không phải grep nội dung file — grep chỉ kiểm chữ, không kiểm hành vi.
    """
    return select(Lead).where(Lead.gift_code == gift_code).with_for_update()


def redeem_gift(db: Session, *, gift_code: str, actor: str) -> RedeemResult:
    """Chuyển gift sang REDEEMED, nguyên tử và idempotent.

    Cách chống double-spend: khoá hàng bằng `SELECT ... FOR UPDATE` TRƯỚC khi
    đọc trạng thái. Ở mức READ COMMITTED, nếu một transaction khác đang giữ
    khoá thì transaction này **chờ**; khi được giải phóng, PostgreSQL đọc lại
    hàng ĐÃ CẬP NHẬT, nên bên thua nhìn thấy `REDEEMED` và trả về idempotent
    thay vì ghi lần thứ hai.
    """
    code = normalize_gift_code(gift_code)

    if not is_well_formed_gift_code(code):
        raise NotFound("GIFT_NOT_FOUND", "Mã quà không đúng định dạng.")

    # Khoá hàng: đây là điểm then chốt của việc chống double-spend.
    stmt = locked_lead_query(code)
    lead = db.execute(stmt).scalar_one_or_none()

    if lead is None:
        raise NotFound("GIFT_NOT_FOUND", "Không tìm thấy mã quà.")

    if lead.gift_status == GiftStatus.CANCELLED.value:
        raise ApiError(
            409,
            "GIFT_CANCELLED",
            "Mã quà này đã bị huỷ. Không phát quà.",
        )

    if lead.gift_status == GiftStatus.REDEEMED.value:
        # Idempotent: KHÔNG ghi gì thêm, KHÔNG đổi `redeemed_at`.
        # Vẫn commit để nhả khoá hàng.
        db.commit()
        logger.info("Mã %s đã được phát trước đó — trả về idempotent", code)
        return RedeemResult(lead=lead, already_redeemed=True)

    if lead.gift_status not in REDEEMABLE_STATUSES:
        raise ApiError(
            409,
            "GIFT_STATUS_NOT_REDEEMABLE",
            f"Mã quà đang ở trạng thái {lead.gift_status}, không phát được.",
        )

    from_status = lead.gift_status
    redeemed_at = datetime.now(UTC)

    lead.gift_status = GiftStatus.REDEEMED.value
    lead.redeemed_at = redeemed_at
    lead.redeemed_by = actor

    record_event(
        db,
        event_type=AuditEventType.GIFT_STATUS_CHANGED,
        actor=actor,
        lead=lead,
        metadata={
            "from_status": from_status,
            "to_status": GiftStatus.REDEEMED.value,
            "outcome": "REDEEMED",
        },
    )
    record_event(
        db,
        event_type=AuditEventType.GIFT_REDEEMED,
        actor=actor,
        lead=lead,
        metadata={
            "from_status": from_status,
            "to_status": GiftStatus.REDEEMED.value,
            "outcome": "REDEEMED",
        },
    )

    # Audit và thay đổi trạng thái nằm CÙNG một transaction: hoặc cùng thành
    # công, hoặc cùng không. Không bao giờ có chuyện phát quà mà không có vết.
    db.commit()
    db.refresh(lead)

    logger.info("Đã phát quà %s (từ %s) bởi %s", code, from_status, actor)
    return RedeemResult(lead=lead, already_redeemed=False)
