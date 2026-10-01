"""Lược đồ dữ liệu vào/ra của API (Pydantic v2).

Nguyên tắc: KHÔNG TIN DỮ LIỆU CLIENT. Mọi giá trị được chuẩn hoá và kiểm
tra lại ở đây, kể cả khi frontend đã kiểm một lần.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .phone import is_valid_vn_mobile, normalize_phone

#: Giá trị tracking cho phép — TRÙNG KHỚP với `assets/js/tracking.js`.
TRACKING_VALUE_RE = re.compile(r"^[A-Za-z0-9._~-]{1,64}$")

TrackingValue = Annotated[str, Field(max_length=64)]


def _clean_tracking(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if not TRACKING_VALUE_RE.match(cleaned):
        raise ValueError(f"{field} chỉ được chứa chữ, số và các ký tự . _ ~ - (tối đa 64 ký tự)")
    return cleaned


class LeadCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=1, max_length=32)

    #: `model_code` trong danh mục iPhone. Server tự tra ra tên hiển thị và năm.
    iphone_model: str = Field(min_length=1, max_length=64)
    case_color: str = Field(min_length=1, max_length=40)

    company_name: str | None = Field(default=None, max_length=120)
    bni_chapter: str | None = Field(default=None, max_length=80)
    referrer_name: str | None = Field(default=None, max_length=80)

    source: TrackingValue | None = None
    campaign: TrackingValue | None = None
    utm_source: TrackingValue | None = None
    utm_medium: TrackingValue | None = None
    utm_campaign: TrackingValue | None = None
    utm_content: TrackingValue | None = None
    ref: TrackingValue | None = None

    #: BẮT BUỘC có mặt và phải là `true`. Không đặt mặc định — nếu đặt mặc
    #: định, việc thiếu trường sẽ lặng lẽ trở thành `false` và validator
    #: không chạy, khiến lead thiếu consent vẫn lọt qua.
    consent: bool

    #: Token Cloudflare Turnstile. Chỉ bắt buộc khi máy chủ đã cấu hình secret.
    turnstile_token: str | None = Field(default=None, max_length=4096)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        normalized = normalize_phone(value)
        if not is_valid_vn_mobile(normalized):
            raise ValueError(
                "Số điện thoại chưa đúng định dạng Việt Nam (10 số, bắt đầu bằng 03/05/07/08/09)"
            )
        return normalized

    @field_validator("consent")
    @classmethod
    def _validate_consent(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Cần có sự đồng ý của khách trước khi lưu thông tin")
        return value

    @field_validator("company_name", "bni_chapter", "referrer_name", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "source",
        "campaign",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "ref",
        mode="before",
    )
    @classmethod
    def _clean_tracking_fields(cls, value: object, info) -> object:
        if value is None:
            return None
        return _clean_tracking(str(value), info.field_name)

    @model_validator(mode="after")
    def _reject_control_characters(self) -> LeadCreateRequest:
        for name in ("full_name", "case_color"):
            raw = getattr(self, name)
            if any(ord(ch) < 32 for ch in raw):
                raise ValueError(f"{name} chứa ký tự điều khiển không hợp lệ")
        return self


class LeadCreateResponse(BaseModel):
    lead_id: uuid.UUID
    gift_code: str
    gift_status: str
    #: `True` khi hệ thống trả lại gift code đang có thay vì tạo gift mới
    #: (chính sách chống trùng). Trường bổ sung, không phá hợp đồng tối thiểu.
    duplicate: bool = False


class GiftLookupResponse(BaseModel):
    """Thông tin TỐI THIỂU cho nhân viên tại quầy.

    Cố ý KHÔNG trả số điện thoại đầy đủ và không trả các trường UTM.
    Cần dữ liệu đầy đủ thì dùng khu vực admin (G05), có xác thực riêng.
    """

    lead_id: uuid.UUID
    gift_code: str
    gift_status: str
    full_name: str
    phone_masked: str
    iphone_model: str
    iphone_year: int
    case_color: str
    created_at: datetime
    redeemed_at: datetime | None = None


class GiftRedeemResponse(BaseModel):
    lead_id: uuid.UUID
    gift_code: str
    gift_status: str
    #: `True` khi mã đã ở trạng thái REDEEMED từ trước — phản hồi idempotent.
    already_redeemed: bool = False
    redeemed_at: datetime | None = None


class CatalogModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    model_code: str
    display_name: str


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: uuid.UUID
    event_type: str
    actor: str
    created_at: datetime
