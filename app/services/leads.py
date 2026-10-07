"""Nghiệp vụ lead: tra danh mục, chính sách chống trùng, sinh gift code."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_event
from ..config import settings
from ..errors import ApiError
from ..giftcodes import generate_gift_code
from ..models import (
    ACTIVE_GIFT_STATUSES,
    AuditEventType,
    GiftStatus,
    IphoneModel,
    Lead,
)
from ..schemas import LeadCreateRequest
from .customers import link_lead_to_customer

logger = logging.getLogger("vipphone.leads")


@dataclass(slots=True)
class LeadCreationResult:
    lead: Lead
    duplicate: bool


def resolve_catalog_model(db: Session, model_code: str) -> IphoneModel | None:
    """Tra model ĐANG HOẠT ĐỘNG trong danh mục.

    Model không có trong danh mục (hoặc đã tắt) bị TỪ CHỐI — không tự bịa
    model mới, không nhận model do client gửi lên.
    """
    stmt = select(IphoneModel).where(
        IphoneModel.model_code == model_code.strip().lower(),
        IphoneModel.active.is_(True),
    )
    return db.execute(stmt).scalar_one_or_none()


def find_active_duplicate(db: Session, *, phone: str, iphone_model: str) -> Lead | None:
    """Tìm lead đang hoạt động trùng (phone + dòng máy).

    Chính sách mặc định: cùng số điện thoại ĐÃ CHUẨN HOÁ + cùng dòng máy +
    `gift_status <> CANCELLED` → trả lại gift hiện có, KHÔNG tạo gift mới.
    """
    stmt = (
        select(Lead)
        .where(
            Lead.phone == phone,
            Lead.iphone_model == iphone_model,
            Lead.gift_status.in_(ACTIVE_GIFT_STATUSES),
        )
        .order_by(Lead.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def create_lead(
    db: Session,
    payload: LeadCreateRequest,
    *,
    actor: str,
    request_id: str | None = None,
) -> LeadCreationResult:
    """Tạo lead + gift code, hoặc trả lại gift đang có nếu trùng."""
    model = resolve_catalog_model(db, payload.iphone_model)
    if model is None:
        raise ApiError(
            422,
            "MODEL_NOT_IN_CATALOG",
            "Dòng iPhone này không có trong danh mục đang hoạt động.",
            fields={"iphone_model": "Chọn dòng máy trong danh sách."},
        )

    phone = payload.phone  # đã chuẩn hoá bởi Pydantic

    existing = find_active_duplicate(db, phone=phone, iphone_model=model.display_name)
    if existing is not None:
        logger.info("Trùng lead, trả lại gift hiện có %s", existing.gift_code)
        return LeadCreationResult(lead=existing, duplicate=True)

    last_error: IntegrityError | None = None

    for attempt in range(settings.gift_code_max_attempts):
        lead = Lead(
            lead_id=uuid.uuid4(),
            gift_code=generate_gift_code(),
            full_name=payload.full_name,
            phone=phone,
            iphone_model=model.display_name,
            iphone_year=model.year,
            case_color=payload.case_color,
            email=payload.email,
            address=payload.address,
            company_name=payload.company_name,
            bni_chapter=payload.bni_chapter,
            referrer_name=payload.referrer_name,
            source=payload.source,
            campaign=payload.campaign,
            utm_source=payload.utm_source,
            utm_medium=payload.utm_medium,
            utm_campaign=payload.utm_campaign,
            utm_content=payload.utm_content,
            ref=payload.ref,
            consent=payload.consent,
            gift_status=GiftStatus.NEW.value,
        )
        db.add(lead)
        try:
            db.flush()
        except IntegrityError as exc:
            last_error = exc
            db.rollback()

            # Sau rollback, kiểm tra xem có phải do TRÙNG LEAD không.
            # Nếu đúng, trả lại gift hiện có — đây mới là kết quả đúng.
            concurrent = find_active_duplicate(db, phone=phone, iphone_model=model.display_name)
            if concurrent is not None:
                logger.info("Đụng độ đồng thời: trả lại gift hiện có %s", concurrent.gift_code)
                return LeadCreationResult(lead=concurrent, duplicate=True)

            logger.warning(
                "Đụng độ gift code (lần thử %d/%d), thử lại",
                attempt + 1,
                settings.gift_code_max_attempts,
            )
            continue

        # G13 — liên kết khách hàng. Việc PHỤ: lỗi ở đây KHÔNG được làm hỏng việc
        # tạo lead. Hàm tự bắt lỗi và ghi log, không ném ra ngoài (ADR-0002 §4).
        link_lead_to_customer(db, lead)

        record_event(
            db,
            event_type=AuditEventType.LEAD_CREATED,
            actor=actor,
            lead=lead,
            metadata={
                "model_code": model.model_code,
                "iphone_year": model.year,
                "source": payload.source,
                "utm_source": payload.utm_source,
                "utm_campaign": payload.utm_campaign,
                "duplicate": False,
            },
        )
        record_event(
            db,
            event_type=AuditEventType.GIFT_CREATED,
            actor=actor,
            lead=lead,
            metadata={
                "model_code": model.model_code,
                "from_status": None,
                "to_status": GiftStatus.NEW.value,
            },
        )

        db.commit()
        db.refresh(lead)
        return LeadCreationResult(lead=lead, duplicate=False)

    # Chỉ ghi LOẠI lỗi: thông điệp lỗi DB có thể chứa dữ liệu dòng (tên, SĐT).
    logger.error(
        "Không sinh được gift code duy nhất sau nhiều lần thử: %s", type(last_error).__name__
    )
    raise ApiError(
        503,
        "GIFT_CODE_EXHAUSTED",
        "Hệ thống chưa sinh được mã quà. Vui lòng thử lại.",
    )
