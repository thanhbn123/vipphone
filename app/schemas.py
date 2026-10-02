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

#: Slug của `model_code` trong danh mục iPhone.
#: Bắt đầu bằng chữ thường hoặc số, sau đó chỉ chữ thường/số/gạch ngang, tối đa 64.
MODEL_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: Năm hợp lý của một dòng iPhone. iPhone đời đầu là 2007 — sớm hơn là dữ liệu rác.
IPHONE_MIN_YEAR = 2007
#: Trần trên để chặn giá trị vô lý (ví dụ 99999). Không phải dự đoán sản phẩm.
IPHONE_MAX_YEAR = 2100

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

    #: Gmail — KHÔNG bắt buộc (xem docs/pii-data-map.md).
    email: str | None = Field(default=None, max_length=254)
    #: Địa chỉ giao hàng, tách sẵn 4 phần cho API vận chuyển.
    address_street: str | None = Field(default=None, max_length=200)
    address_ward: str | None = Field(default=None, max_length=120)
    address_district: str | None = Field(default=None, max_length=120)
    address_province: str | None = Field(default=None, max_length=120)
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

    @field_validator(
        "email",
        "address_street",
        "address_ward",
        "address_district",
        "address_province",
        mode="before",
    )
    @classmethod
    def _blank_becomes_none(cls, value: object) -> object:
        """Ô để trống ⇒ lưu NULL, KHÔNG lưu chuỗi rỗng.

        Vì sao quan trọng: `''` và `NULL` khác nhau khi truy vấn. Lưu `''` thì
        `WHERE address_street IS NULL` (lọc "chưa có địa chỉ" để biết đơn nào lên
        được) sẽ **bỏ sót** đúng những dòng cần tìm.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        """Gmail không bắt buộc, nhưng ĐIỀN thì phải đúng dạng.

        Cố ý không dùng `EmailStr`: nó cần gói `email-validator`, và thêm một phụ
        thuộc CHẠY THẬT chỉ để kiểm một trường không bắt buộc là cái giá không đáng
        — nhất là sau STG-1 (một phụ thuộc runtime khai thiếu làm sập cả ứng dụng).
        """
        if value is None or not value.strip():
            return None
        candidate = value.strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", candidate):
            raise ValueError("Gmail chưa đúng dạng (ví dụ: ten@gmail.com)")
        return candidate.lower()

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


# --------------------------------------------------------------------------
# KHU VỰC QUẢN TRỊ (G05/G06) — MỌI route dùng các lược đồ này PHẢI có xác thực.
# --------------------------------------------------------------------------


class AdminLeadOut(BaseModel):
    """Bản ghi ĐẦY ĐỦ của một lead.

    Khác `GiftLookupResponse` (dành cho quầy, che SĐT): đây là khu vực quản trị
    có xác thực riêng, nên trả đủ trường để đối soát và xuất báo cáo. Ranh giới
    nằm ở XÁC THỰC, không nằm ở việc che bớt trường.
    """

    model_config = ConfigDict(from_attributes=True)

    lead_id: uuid.UUID
    gift_code: str
    gift_status: str
    full_name: str
    phone: str
    iphone_model: str
    iphone_year: int
    case_color: str
    email: str | None = None
    address_street: str | None = None
    address_ward: str | None = None
    address_district: str | None = None
    address_province: str | None = None
    company_name: str | None = None
    bni_chapter: str | None = None
    referrer_name: str | None = None
    source: str | None = None
    campaign: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    ref: str | None = None
    consent: bool
    created_at: datetime
    updated_at: datetime
    redeemed_at: datetime | None = None
    redeemed_by: str | None = None


class AdminLeadPageOut(BaseModel):
    """Một trang kết quả + TỔNG SỐ, để UI phân trang mà không phải đoán."""

    items: list[AdminLeadOut]
    total: int
    page: int
    page_size: int


def _validate_model_code(value: str) -> str:
    """Slug của `model_code`: chữ thường, số, gạch ngang; 1..64 ký tự."""
    cleaned = value.strip().lower()
    if not MODEL_CODE_RE.match(cleaned):
        raise ValueError(
            "model_code chỉ được gồm chữ thường a-z, chữ số 0-9 và dấu gạch ngang, "
            "bắt đầu bằng chữ hoặc số, tối đa 64 ký tự (ví dụ: iphone-17-pro)"
        )
    return cleaned


class IphoneModelCreateRequest(BaseModel):
    """Thêm model vào DANH MỤC — không tự bịa model nào ngoài dữ liệu admin nhập.

    Không có giá trị nào sinh ra model: mọi trường do admin nhập. Hệ thống KHÔNG
    suy đoán model kế tiếp từ model đang có, cũng không seed sẵn.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    model_code: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=120)
    year: int = Field(ge=IPHONE_MIN_YEAR, le=IPHONE_MAX_YEAR)
    active: bool = True
    sort_order: int = Field(default=0, ge=-10_000, le=10_000)

    @field_validator("model_code")
    @classmethod
    def _check_model_code(cls, value: str) -> str:
        return _validate_model_code(value)

    @field_validator("display_name")
    @classmethod
    def _check_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name không được để trống")
        if any(ord(ch) < 32 for ch in cleaned):
            raise ValueError("display_name chứa ký tự điều khiển không hợp lệ")
        return cleaned


class IphoneModelPatchRequest(BaseModel):
    """Sửa model đang có. KHÔNG cho sửa `model_code` và `year`.

    `model_code` là khoá tra cứu mà landing và lead đang dùng; đổi nó là làm gãy
    dữ liệu cũ. `year` gắn với model chứ không phải thuộc tính sửa nhanh. Cần
    khác thì tạo model mới.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=-10_000, le=10_000)

    @field_validator("display_name")
    @classmethod
    def _check_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name không được để trống")
        if any(ord(ch) < 32 for ch in cleaned):
            raise ValueError("display_name chứa ký tự điều khiển không hợp lệ")
        return cleaned

    @model_validator(mode="after")
    def _at_least_one_field(self) -> IphoneModelPatchRequest:
        if self.display_name is None and self.active is None and self.sort_order is None:
            raise ValueError("Cần gửi ít nhất một trường để sửa.")
        return self


class AdminIphoneModelOut(BaseModel):
    """Model trả về cho khu vực quản trị (khác bản công khai: có `active`, `sort_order`)."""

    model_config = ConfigDict(from_attributes=True)

    year: int
    model_code: str
    display_name: str
    active: bool
    sort_order: int
