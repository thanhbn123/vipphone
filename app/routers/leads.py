"""API thu lead."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..audit import derive_actor_from_request
from ..db import get_db
from ..errors import ApiError, ValidationFailed
from ..limits import read_limited_body
from ..schemas import LeadCreateRequest, LeadCreateResponse
from ..security import client_ip, enforce_lead_rate_limit, verify_turnstile
from ..services.leads import create_lead

logger = logging.getLogger("vipphone.api.leads")

router = APIRouter(prefix="/api", tags=["leads"])

#: Ánh xạ tên trường của Pydantic sang tên trường phía client, để frontend
#: gắn lỗi đúng ô nhập liệu.
_FIELD_ALIASES = {
    "iphone_model": "iphone_model",
    "full_name": "full_name",
    "phone": "phone",
    "case_color": "case_color",
    "consent": "consent",
}


def _field_errors(exc: ValidationError) -> dict[str, str]:
    fields: dict[str, str] = {}
    for error in exc.errors():
        location = [part for part in error["loc"] if isinstance(part, str)]
        name = location[-1] if location else "body"
        message = error.get("msg", "Giá trị không hợp lệ")
        # Pydantic bọc thông báo của validator; bỏ tiền tố cho dễ đọc.
        message = message.removeprefix("Value error, ")
        fields[_FIELD_ALIASES.get(name, name)] = message
    return fields


@router.post(
    "/leads",
    response_model=LeadCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo lead và cấp gift code",
)
async def create_lead_endpoint(
    request: Request,
    db: Session = Depends(get_db),
) -> LeadCreateResponse:
    """Tạo lead. KHÔNG TIN DỮ LIỆU CLIENT.

    Mọi giá trị đều được kiểm lại ở server: chuẩn hoá số điện thoại, tra
    dòng máy trong danh mục đang hoạt động, bắt buộc có consent, giới hạn
    độ dài, whitelist giá trị tracking.
    """
    enforce_lead_rate_limit(request)

    # Đọc body qua trần chặn — kiểm Content-Length TRƯỚC khi đọc (xem app/limits.py).
    raw = await read_limited_body(request, request.app.state.settings.max_lead_body_bytes)

    try:
        body = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise ApiError(400, "INVALID_JSON", "Body không phải JSON hợp lệ.") from exc

    if not isinstance(body, dict):
        raise ApiError(400, "INVALID_JSON", "Body phải là một đối tượng JSON.")

    try:
        payload = LeadCreateRequest.model_validate(body)
    except ValidationError as exc:
        raise ValidationFailed(_field_errors(exc)) from exc

    await verify_turnstile(payload.turnstile_token, client_ip(request))

    result = create_lead(
        db,
        payload,
        actor=derive_actor_from_request(request),
    )

    logger.info(
        "Lead %s (duplicate=%s) từ %s",
        result.lead.gift_code,
        result.duplicate,
        client_ip(request),
    )

    return LeadCreateResponse(
        lead_id=result.lead.lead_id,
        gift_code=result.lead.gift_code,
        gift_status=result.lead.gift_status,
        duplicate=result.duplicate,
    )
