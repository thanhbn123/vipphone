"""Ghi audit trail cho các thay đổi quan trọng.

CẤM ghi secret. CẤM ghi PII dư thừa. Để tránh rò rỉ do sơ suất về sau, phần
`metadata` đi qua một DANH SÁCH TRẮNG khoá — khoá lạ bị loại bỏ và ghi log,
chứ không được lưu.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditEvent, AuditEventType, Lead
from .phone import normalize_phone

logger = logging.getLogger("vipphone.audit")

#: Chỉ những khoá này được phép xuất hiện trong `metadata`.
ALLOWED_METADATA_KEYS = frozenset(
    {
        "model_code",
        "iphone_year",
        "source",
        "utm_source",
        "utm_campaign",
        "duplicate",
        "from_status",
        "to_status",
        "reason",
        "outcome",
        "rate_limited",
        "turnstile",
    }
)

#: Khoá bị chặn tuyệt đối, kể cả khi lọt vào danh sách trắng do sửa nhầm.
FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "phone",
        "full_name",
        "company_name",
        "bni_chapter",
        "referrer_name",
        "email",
        "secret",
        "token",
        "api_key",
        "password",
    }
)


def scrub_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None

    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in FORBIDDEN_METADATA_KEYS or key not in ALLOWED_METADATA_KEYS:
            logger.warning("Bỏ khoá metadata không được phép: %r", key)
            continue
        if value is None:
            continue
        clean[key] = value

    return clean or None


def record_event(
    db: Session,
    *,
    event_type: AuditEventType | str,
    actor: str,
    lead: Lead | None = None,
    gift_code: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Thêm một bản ghi audit vào session hiện tại (chưa commit).

    Người gọi chịu trách nhiệm commit CÙNG transaction với thay đổi nghiệp vụ,
    để audit và dữ liệu không bao giờ lệch nhau.
    """
    event = AuditEvent(
        event_id=uuid.uuid4(),
        event_type=str(event_type),
        lead_pk=lead.id if lead is not None else None,
        lead_id=lead.lead_id if lead is not None else None,
        gift_code=gift_code or (lead.gift_code if lead is not None else None),
        actor=actor,
        event_metadata=scrub_metadata(metadata),
    )
    db.add(event)
    return event


def derive_actor_from_request(request) -> str:  # pragma: no cover - tiện ích
    """Nhãn actor cho hành động công khai (khách tự đăng ký)."""
    from .security import client_ip

    try:
        return f"public:{client_ip(request)}"
    except Exception:
        return "public:unknown"


def phone_fingerprint(phone: str) -> str:
    """Vân tay KHÔNG thể đảo ngược của số điện thoại, dùng khi cần đối chiếu
    trong audit mà không được lưu số thật."""
    import hashlib

    return hashlib.sha256(normalize_phone(phone).encode("utf-8")).hexdigest()[:12]
