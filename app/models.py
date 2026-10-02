"""Mô hình dữ liệu VIP PHONE.

Schema thật do Alembic tạo (xem `migrations/`). KHÔNG gọi `create_all()`
ở môi trường thật — xem ADR-0001 §3.2.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class GiftStatus(StrEnum):
    NEW = "NEW"
    CONFIRMED = "CONFIRMED"
    READY = "READY"
    REDEEMED = "REDEEMED"
    CANCELLED = "CANCELLED"


GIFT_STATUS_VALUES = tuple(status.value for status in GiftStatus)

#: Trạng thái còn "đang hoạt động" — dùng cho chính sách chống trùng.
ACTIVE_GIFT_STATUSES = tuple(
    status.value for status in GiftStatus if status is not GiftStatus.CANCELLED
)


class AuditEventType(StrEnum):
    LEAD_CREATED = "LEAD_CREATED"
    GIFT_CREATED = "GIFT_CREATED"
    GIFT_STATUS_CHANGED = "GIFT_STATUS_CHANGED"
    GIFT_REDEEMED = "GIFT_REDEEMED"


class IphoneModel(Base):
    """Danh mục iPhone. Admin thêm model mới mà KHÔNG phải sửa HTML landing."""

    __tablename__ = "iphone_models"
    __table_args__ = (
        UniqueConstraint("model_code", name="uq_iphone_models_model_code"),
        Index("ix_iphone_models_active_sort", "active", "sort_order"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    model_code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "gift_status IN ('NEW','CONFIRMED','READY','REDEEMED','CANCELLED')",
            name="ck_leads_gift_status",
        ),
        CheckConstraint("consent IS TRUE", name="ck_leads_consent_true"),
        CheckConstraint("phone ~ '^0[35789][0-9]{8}$'", name="ck_leads_phone_canonical"),
        # Các index này PHẢI khai ở đây với ĐÚNG tên trong migration, nếu không
        # `alembic check` sẽ báo lệch (nó tưởng migration thừa index).
        Index("ix_leads_phone", "phone"),
        Index("ix_leads_created_at", "created_at"),
        Index("ix_leads_gift_status", "gift_status"),
        Index("ix_leads_dup", "phone", "iphone_model", "gift_status"),
        # Chính sách chống trùng được ÉP Ở TẦNG DATABASE, không chỉ ở tầng ứng dụng.
        # Một phần tử UNIQUE: cùng (phone, iphone_model) chỉ được có MỘT gift
        # chưa huỷ. Nhờ vậy hai request đồng thời cũng không tạo được hai gift.
        Index(
            "uq_leads_active_duplicate",
            "phone",
            "iphone_model",
            unique=True,
            postgresql_where=text("gift_status <> 'CANCELLED'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    gift_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    full_name: Mapped[str] = mapped_column(String(80), nullable=False)
    phone: Mapped[str] = mapped_column(String(16), nullable=False)
    iphone_model: Mapped[str] = mapped_column(String(120), nullable=False)
    iphone_year: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Màu ốp khách muốn. Nay là GHI CHÚ TỰ DO nên cho phép rỗng (migration 0004).
    #: Sau này có ảnh mẫu để chọn thì giá trị chọn vẫn ghi vào CHÍNH cột này.
    case_color: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # --- Liên hệ & địa chỉ giao hàng (UI-2) -------------------------------
    #: Gmail khách. KHÔNG bắt buộc — bắt buộc sẽ làm rớt khách tại quầy.
    email: Mapped[str | None] = mapped_column(String(254))
    #: Địa chỉ TÁCH SẴN 4 phần, khớp thẳng API đơn vị vận chuyển
    #: (Viettel Post cần PROVINCE / DISTRICT / WARD / ADDRESS riêng).
    #: Cố ý KHÔNG hard-code danh mục tỉnh/phường: Việt Nam vừa sáp nhập đơn vị
    #: hành chính nên mọi danh sách chép tay đều có nguy cơ sai; để dạng text,
    #: sau này nối dropdown vào API của hãng vận chuyển (nguồn chuẩn của họ).
    address_street: Mapped[str | None] = mapped_column(String(200))
    address_ward: Mapped[str | None] = mapped_column(String(120))
    address_district: Mapped[str | None] = mapped_column(String(120))
    address_province: Mapped[str | None] = mapped_column(String(120))
    company_name: Mapped[str | None] = mapped_column(String(120))
    bni_chapter: Mapped[str | None] = mapped_column(String(80))
    referrer_name: Mapped[str | None] = mapped_column(String(80))

    source: Mapped[str | None] = mapped_column(String(32))
    campaign: Mapped[str | None] = mapped_column(String(64))
    utm_source: Mapped[str | None] = mapped_column(String(64))
    utm_medium: Mapped[str | None] = mapped_column(String(64))
    utm_campaign: Mapped[str | None] = mapped_column(String(64))
    utm_content: Mapped[str | None] = mapped_column(String(64))
    ref: Mapped[str | None] = mapped_column(String(64))

    consent: Mapped[bool] = mapped_column(Boolean, nullable=False)

    gift_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'NEW'")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redeemed_by: Mapped[str | None] = mapped_column(String(120))


class AuditEvent(Base):
    """Audit trail cho mọi thay đổi quan trọng.

    CẤM ghi secret và CẤM ghi PII dư thừa vào `event_metadata`.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('LEAD_CREATED','GIFT_CREATED','GIFT_STATUS_CHANGED','GIFT_REDEEMED')",
            name="ck_audit_events_event_type",
        ),
        Index("ix_audit_events_gift_code_created", "gift_code", "created_at"),
        Index("ix_audit_events_lead_id", "lead_id"),
        Index("ix_audit_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)

    lead_pk: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("leads.id", ondelete="SET NULL")
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    gift_code: Mapped[str | None] = mapped_column(String(32))

    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    # `metadata` là tên dành riêng của Declarative nên thuộc tính Python phải
    # đặt tên khác; tên cột trong DB vẫn là `metadata`.
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "ACTIVE_GIFT_STATUSES",
    "GIFT_STATUS_VALUES",
    "AuditEvent",
    "AuditEventType",
    "Base",
    "GiftStatus",
    "IphoneModel",
    "Lead",
    "Text",
]
