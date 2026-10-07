"""Lược đồ dữ liệu vào/ra của API (Pydantic v2).

Nguyên tắc: KHÔNG TIN DỮ LIỆU CLIENT. Mọi giá trị được chuẩn hoá và kiểm
tra lại ở đây, kể cả khi frontend đã kiểm một lần.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

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
    #: Ô GHI CHÚ màu mong muốn — KHÔNG bắt buộc (migration 0004).
    case_color: str | None = Field(default=None, max_length=40)

    #: Gmail — KHÔNG bắt buộc (xem docs/pii-data-map.md).
    email: str | None = Field(default=None, max_length=254)
    #: Địa chỉ nhận hàng — MỘT ô tự do.
    address: str | None = Field(default=None, max_length=300)
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
        "address",
        mode="before",
    )
    @classmethod
    def _blank_becomes_none(cls, value: object) -> object:
        """Ô để trống ⇒ lưu NULL, KHÔNG lưu chuỗi rỗng.

        Vì sao quan trọng: `''` và `NULL` khác nhau khi truy vấn. Lưu `''` thì
        `WHERE address IS NULL` (lọc "chưa có địa chỉ" để biết đơn nào lên
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
            if raw is None:  # case_color không bắt buộc
                continue
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
    case_color: str | None = None
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
    case_color: str | None = None
    email: str | None = None
    address: str | None = None
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


# ============================================================================
# G13 — Khách hàng (Customer 360)
# ============================================================================
class CustomerDeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_code: str | None = None
    display_name: str
    year: int | None = None
    is_primary: bool


class CustomerAcquisitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str | None = None
    referrer_name: str | None = None
    ref: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    first_gift_code: str | None = None
    campaign: str | None = None
    acquired_via: str | None = None


class CustomerOut(BaseModel):
    """Hồ sơ khách rút gọn cho danh sách. KHÔNG có PII nặng."""

    model_config = ConfigDict(from_attributes=True)

    customer_id: uuid.UUID
    full_name: str
    phone_masked: str
    status: str
    marketing_consent: bool
    created_at: datetime


class CustomerGiftOut(BaseModel):
    gift_code: str
    iphone_model: str
    gift_status: str
    created_at: datetime
    redeemed_at: datetime | None = None


class CustomerOrderOut(BaseModel):
    """Đơn của khách trong Customer 360 — bản tóm tắt, không địa chỉ."""

    order_id: uuid.UUID
    order_number: str
    status: str
    payment_status: str
    grand_total: Decimal
    currency: str
    source: str | None = None
    created_at: datetime


class CustomerDetailOut(CustomerOut):
    """Customer 360: thiết bị, nguồn đầu tiên, lịch sử quà, ĐƠN HÀNG (G16)."""

    email: str | None = None
    company_name: str | None = None
    bni_chapter: str | None = None
    consent_updated_at: datetime | None = None
    devices: list[CustomerDeviceOut] = []
    acquisition: CustomerAcquisitionOut | None = None
    gift_history: list[CustomerGiftOut] = []
    orders: list[CustomerOrderOut] = []


# ============================================================================
# G14 — DANH MỤC SẢN PHẨM. Thiết kế: `docs/catalog.md`.
#
# HAI LƯỢC ĐỒ TÁCH HẲN: `ProductOut` (công khai) và `AdminProductOut` (quản trị).
# Không dùng chung một lược đồ rồi "ẩn bớt trường" — đó là cách chắc chắn nhất để
# một ngày nào đó `cost_price` lọt ra ngoài.
# ============================================================================

#: Slug sản phẩm: chữ thường, số, gạch ngang; không gạch ở đầu/cuối.
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

#: Mã SKU: chữ HOA, số, gạch ngang; không gạch ở đầu/cuối.
SKU_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")

#: Mã category: chữ HOA, số, gạch dưới.
CATEGORY_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,39}$")

#: Tiền: `Decimal`, tối đa 10 chữ số phần nguyên + ĐÚNG 2 chữ số thập phân.
#: KHÔNG dùng `float` — xem `docs/catalog.md` §3.1.
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]

#: Mặc định và giá trị cho phép của `compatibility_type`.
COMPATIBILITY_TYPES = ("FULL", "PARTIAL", "CASE_FIT")

#: Nhãn tồn kho. CHỈ hai giá trị này — G14 chưa có inventory engine nên TUYỆT ĐỐI
#: không có số lượng. Đổi tập này thì sửa `docs/catalog.md` §7.3 trước.
AVAILABILITY_IN_STOCK = "IN_STOCK"
AVAILABILITY_OUT_OF_STOCK = "OUT_OF_STOCK"


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    sort_order: int


class CompatibilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_brand: str
    device_model_code: str
    compatibility_type: str


class VariantOut(BaseModel):
    """SKU nhìn từ phía CÔNG KHAI: KHÔNG có `cost_price`, KHÔNG có cờ nội bộ.

    Đường công khai CHỈ trả SKU `active = true`, nên mọi SKU có mặt ở đây đều
    mua được. Nhãn Còn/Hết hàng nằm ở CẤP SẢN PHẨM — xem `ProductOut.availability`.
    """

    sku: str
    variant_name: str
    color: str | None = None
    sale_price: Decimal
    compare_at_price: Decimal | None = None
    currency: str
    compatibility: list[CompatibilityOut] = []


class ProductImageOut(BaseModel):
    """Ảnh — bản công khai. `url` là đường dẫn CÙNG ORIGIN (`/media/...`)."""

    url: str
    alt_text: str
    is_primary: bool
    width: int
    height: int


class AdminProductImageOut(ProductImageOut):
    image_id: uuid.UUID
    sort_order: int
    content_type: str
    byte_size: int


class ProductOut(BaseModel):
    product_id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    brand: str | None = None
    category: CategoryOut | None = None
    #: `IN_STOCK` khi có ÍT NHẤT MỘT SKU active, ngược lại `OUT_OF_STOCK`.
    #: Đây là trạng thái BÁN ĐƯỢC hay không — KHÔNG phải số lượng tồn kho.
    #: G14 chưa có inventory engine nên TUYỆT ĐỐI không có con số nào ở đây.
    availability: str
    variants: list[VariantOut] = []
    #: Ảnh chính đứng đầu, rồi theo `sort_order`.
    images: list[ProductImageOut] = []


class ProductPageOut(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int


class AdminCompatibilityOut(CompatibilityOut):
    """Bản quản trị của khai báo tương thích — THÊM `id` để gỡ được khai báo sai.

    `id` là khoá nội bộ nên CHỈ có ở đây, không có ở lược đồ công khai.
    """

    id: int


class AdminVariantOut(VariantOut):
    """Bản quản trị: THÊM cờ nội bộ, `cost_price`, và `id` của khai báo tương thích."""

    active: bool
    stock_tracking: bool
    cost_price: Decimal | None = None
    compatibility: list[AdminCompatibilityOut] = []


class AdminProductOut(ProductOut):
    active: bool
    created_at: datetime
    updated_at: datetime
    variants: list[AdminVariantOut] = []
    images: list[AdminProductImageOut] = []


class AdminProductPageOut(BaseModel):
    items: list[AdminProductOut]
    total: int
    page: int
    page_size: int


def _validate_slug(value: str) -> str:
    cleaned = value.strip().lower()
    if not SLUG_RE.match(cleaned):
        raise ValueError(
            "slug chỉ được gồm chữ thường a-z, chữ số 0-9 và dấu gạch ngang giữa các từ "
            "(ví dụ: op-iphone-16-pro-max)"
        )
    return cleaned


def _validate_sku(value: str) -> str:
    cleaned = value.strip().upper()
    if not SKU_RE.match(cleaned):
        raise ValueError(
            "sku chỉ được gồm chữ HOA A-Z, chữ số 0-9 và dấu gạch ngang giữa các phần "
            "(ví dụ: OP-16PM-DEN)"
        )
    return cleaned


def _validate_category_code(value: str) -> str:
    cleaned = value.strip().upper()
    if not CATEGORY_CODE_RE.match(cleaned):
        raise ValueError("category_code là chữ HOA, số và gạch dưới (ví dụ: CASE)")
    return cleaned


class ProductCreateRequest(BaseModel):
    """Tạo sản phẩm. Mọi trường do admin nhập — hệ thống KHÔNG bịa sản phẩm nào."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=1, max_length=160)
    category_code: str = Field(min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=4000)
    brand: str | None = Field(default=None, max_length=80)
    active: bool = True

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, value: str) -> str:
        return _validate_slug(value)

    @field_validator("category_code")
    @classmethod
    def _check_category_code(cls, value: str) -> str:
        return _validate_category_code(value)

    @field_validator("description", "brand", mode="before")
    @classmethod
    def _blank_becomes_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ProductPatchRequest(BaseModel):
    """Sửa sản phẩm. KHÔNG cho sửa `slug` — slug là khoá tra cứu công khai.

    Đổi slug là làm gãy mọi liên kết đã chia sẻ và mọi đơn hàng đang trỏ tới nó.
    Cần slug khác thì tạo sản phẩm mới và tắt sản phẩm cũ.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=160)
    category_code: str | None = Field(default=None, min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=4000)
    brand: str | None = Field(default=None, max_length=80)
    active: bool | None = None

    @field_validator("category_code")
    @classmethod
    def _check_category_code(cls, value: str | None) -> str | None:
        return None if value is None else _validate_category_code(value)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> ProductPatchRequest:
        if (
            self.name is None
            and self.category_code is None
            and self.description is None
            and self.brand is None
            and self.active is None
        ):
            raise ValueError("Cần gửi ít nhất một trường để sửa.")
        return self


class VariantCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sku: str = Field(min_length=1, max_length=64)
    variant_name: str = Field(min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=40)
    cost_price: Money | None = None
    sale_price: Money
    compare_at_price: Money | None = None
    currency: str = Field(default="VND", min_length=3, max_length=3)
    active: bool = True
    stock_tracking: bool = False

    @field_validator("sku")
    @classmethod
    def _check_sku(cls, value: str) -> str:
        return _validate_sku(value)

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", cleaned):
            raise ValueError("currency là mã tiền tệ 3 chữ HOA (ví dụ: VND)")
        return cleaned

    @field_validator("color", mode="before")
    @classmethod
    def _blank_color(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _compare_at_not_below_sale(self) -> VariantCreateRequest:
        """Giá gạch < giá bán là NÓI DỐI khách. DB cũng chặn, nhưng chặn sớm hơn
        thì thông báo lỗi rõ ràng hơn (422 kèm tên trường, thay vì 500 từ DB)."""
        if self.compare_at_price is not None and self.compare_at_price < self.sale_price:
            raise ValueError("compare_at_price (giá gạch) không được nhỏ hơn sale_price")
        return self


class VariantPatchRequest(BaseModel):
    """Sửa SKU. KHÔNG cho sửa `sku` (mã hàng là khoá tra cứu) và không sửa `product_id`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    variant_name: str | None = Field(default=None, min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=40)
    cost_price: Money | None = None
    sale_price: Money | None = None
    compare_at_price: Money | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    active: bool | None = None
    stock_tracking: bool | None = None
    #: Lý do đổi giá — ghi vào `price_history.reason`. Không bắt buộc.
    price_change_reason: str | None = Field(default=None, max_length=300)

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", cleaned):
            raise ValueError("currency là mã tiền tệ 3 chữ HOA (ví dụ: VND)")
        return cleaned

    @field_validator("color", mode="before")
    @classmethod
    def _blank_color(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _at_least_one_field(self) -> VariantPatchRequest:
        if all(
            getattr(self, name) is None
            for name in (
                "variant_name",
                "color",
                "cost_price",
                "sale_price",
                "compare_at_price",
                "currency",
                "active",
                "stock_tracking",
            )
        ):
            raise ValueError("Cần gửi ít nhất một trường để sửa.")
        return self


class CompatibilityCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    device_brand: str = Field(default="Apple", min_length=1, max_length=40)
    #: MÃ máy (`iphone-16-pro-max`), KHÔNG phải tên hiển thị. Dùng CHUNG
    #: `MODEL_CODE_RE` với danh mục iPhone: hai quy tắc là hai quy tắc sẽ lệch nhau.
    device_model_code: str = Field(min_length=1, max_length=64)
    compatibility_type: str = Field(default="FULL", min_length=1, max_length=20)

    @field_validator("device_model_code")
    @classmethod
    def _check_device_model_code(cls, value: str) -> str:
        return _validate_model_code(value)

    @field_validator("compatibility_type")
    @classmethod
    def _check_compatibility_type(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in COMPATIBILITY_TYPES:
            raise ValueError(
                "compatibility_type phải là một trong: " + ", ".join(COMPATIBILITY_TYPES)
            )
        return cleaned


# ============================================================================
# G15 — GỢI Ý PHỤ KIỆN. Thiết kế: `docs/recommendation-engine.md`.
#
# Lược đồ CÔNG KHAI: chỉ theo MÁY, KHÔNG có trường nào về khách (không phone,
# không email, không tên). `product` là CHÍNH `ProductOut` của G14 — nên
# `cost_price` không thể lọt vào đây.
# ============================================================================
class RecommendationItemOut(BaseModel):
    #: Hạng 1..n theo đúng thứ tự trả về — để tracking ghi được vị trí đã click.
    rank: int
    category_code: str
    product: ProductOut


class RecommendationsOut(BaseModel):
    context: str
    device_model_code: str
    items: list[RecommendationItemOut]


# ============================================================================
# G16 — GIỎ HÀNG + ĐƠN HÀNG. Thiết kế: `docs/commerce.md`.
#
# LUẬT: KHÔNG có trường nào nhận GIÁ hay TỔNG TIỀN để TÍNH. `expected_total` chỉ
# là con số khách ĐÃ THẤY — máy chủ so với tổng tự tính, lệch thì từ chối (409),
# không bao giờ dùng nó làm giá.
# ============================================================================
SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,63}$")


def _clean_sku(value: str) -> str:
    cleaned = str(value).strip().upper()
    if not SKU_RE.match(cleaned):
        raise ValueError("Mã SKU không hợp lệ")
    return cleaned


def _required_text(value: str | None, field: str) -> str:
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        raise ValueError(f"{field} là bắt buộc")
    return cleaned


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _canonical_phone(value: str) -> str:
    if not is_valid_vn_mobile(value):
        raise ValueError("Số điện thoại di động Việt Nam không hợp lệ")
    return normalize_phone(value)


class CartItemAddRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(default=1, ge=1, le=99)

    @field_validator("sku")
    @classmethod
    def _sku(cls, value: str) -> str:
        return _clean_sku(value)


class CartItemUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(ge=1, le=99)


class CartItemOut(BaseModel):
    sku: str
    product_name: str
    product_slug: str
    variant_name: str
    quantity: int
    #: Giá HIỆN HÀNH của SKU — chỉ để hiển thị; đơn sẽ chụp lại giá lúc đặt.
    unit_price: Decimal
    line_total: Decimal
    currency: str
    #: `False` khi SKU/sản phẩm đã tắt — dòng này KHÔNG được tính vào tổng và chặn checkout.
    available: bool


class CartOut(BaseModel):
    cart_id: uuid.UUID
    status: str
    currency: str
    items: list[CartItemOut]
    item_count: int
    subtotal: Decimal
    #: Phí giao hàng + tổng DỰ KIẾN theo giá hiện hành. Checkout tính LẠI từ đầu;
    #: trang checkout gửi `grand_total` này làm `expected_total` để bắt giá đổi.
    shipping_fee: Decimal
    grand_total: Decimal


class CartCreatedOut(CartOut):
    #: Token sở hữu — CHỈ trả MỘT LẦN lúc tạo. Máy chủ chỉ giữ SHA-256 của nó.
    cart_token: str


class CheckoutCustomerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=1, max_length=32)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _required_text(value, "Họ tên")

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return _canonical_phone(value)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        cleaned = _optional_text(value)
        if cleaned is None:
            return None
        cleaned = cleaned.lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", cleaned):
            raise ValueError("Email không hợp lệ")
        return cleaned


class ShippingAddressIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=1, max_length=32)
    address_line: str = Field(min_length=5, max_length=300)
    ward: str | None = Field(default=None, max_length=80)
    district: str | None = Field(default=None, max_length=80)
    province: str = Field(min_length=2, max_length=80)

    @field_validator("recipient_name")
    @classmethod
    def _recipient(cls, value: str) -> str:
        return _required_text(value, "Người nhận")

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return _canonical_phone(value)

    @field_validator("address_line")
    @classmethod
    def _address(cls, value: str) -> str:
        cleaned = _required_text(value, "Địa chỉ")
        if len(cleaned) < 5:
            raise ValueError("Địa chỉ quá ngắn")
        return cleaned

    @field_validator("province")
    @classmethod
    def _province(cls, value: str) -> str:
        cleaned = _required_text(value, "Tỉnh/Thành phố")
        if len(cleaned) < 2:
            raise ValueError("Tỉnh/Thành phố không hợp lệ")
        return cleaned

    @field_validator("ward", "district")
    @classmethod
    def _optional(cls, value: str | None) -> str | None:
        return _optional_text(value)


class AttributionIn(BaseModel):
    """Nguồn của LẦN ĐẶT NÀY (whitelist + làm sạch y như form lead)."""

    model_config = ConfigDict(extra="forbid")

    source: TrackingValue | None = None
    campaign: TrackingValue | None = None
    ref: TrackingValue | None = None
    utm_source: TrackingValue | None = None
    utm_medium: TrackingValue | None = None
    utm_campaign: TrackingValue | None = None
    utm_content: TrackingValue | None = None

    @field_validator(
        "source", "campaign", "ref", "utm_source", "utm_medium", "utm_campaign", "utm_content"
    )
    @classmethod
    def _clean(cls, value: str | None, info) -> str | None:
        cleaned = _clean_tracking(value, info.field_name)
        if cleaned is not None and info.field_name == "source":
            cleaned = cleaned[:32]
        return cleaned


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cart_id: uuid.UUID
    customer: CheckoutCustomerIn
    shipping: ShippingAddressIn
    customer_note: str | None = Field(default=None, max_length=500)
    #: G17 — phương thức thanh toán. `STAGING_MOCK` chỉ nhận khi máy chủ bật giả lập.
    payment_method: Literal["COD", "BANK_TRANSFER_MANUAL", "STAGING_MOCK"] = "COD"
    #: Attribution của lần đặt (last-touch). Không bắt buộc.
    attribution: AttributionIn | None = None
    #: Tổng khách ĐÃ THẤY trên màn hình. KHÔNG dùng để tính tiền — chỉ để phát
    #: hiện giá đổi giữa lúc xem và lúc đặt (lệch ⇒ 409 `PRICE_CHANGED`).
    expected_total: Money | None = None

    @field_validator("customer_note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return _optional_text(value)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str
    product_name: str
    variant_name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class PaymentPublicOut(BaseModel):
    """Khoản thu — bản cho chủ đơn. KHÔNG có dữ liệu tài khoản/thẻ nào."""

    method: str
    status: str
    amount: Decimal
    currency: str
    #: Mã tham chiếu của cổng (chỉ STAGING_MOCK có).
    provider_reference: str | None = None
    instructions: str | None = None


class OrderOut(BaseModel):
    """Đơn — bản cho CHÍNH chủ đơn (có token). Không có PII đầy đủ."""

    order_id: uuid.UUID
    order_number: str
    status: str
    payment_status: str
    currency: str
    subtotal: Decimal
    shipping_fee: Decimal
    discount_total: Decimal
    grand_total: Decimal
    items: list[OrderItemOut]
    recipient_name: str
    phone_masked: str
    province: str
    created_at: datetime
    payment: PaymentPublicOut | None = None


class CheckoutOut(OrderOut):
    #: `True` khi đây là phản hồi PHÁT LẠI của cùng `Idempotency-Key`.
    replayed: bool = False


class OrderStatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field: str
    from_value: str | None
    to_value: str
    actor: str
    reason: str | None
    created_at: datetime


class AdminShippingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recipient_name: str
    phone: str
    address_line: str
    ward: str | None
    district: str | None
    province: str


class AdminOrderSummaryOut(BaseModel):
    order_id: uuid.UUID
    order_number: str
    status: str
    payment_status: str
    grand_total: Decimal
    currency: str
    item_count: int
    customer_id: uuid.UUID
    customer_name: str
    phone_masked: str
    created_at: datetime


class AdminOrderPageOut(BaseModel):
    items: list[AdminOrderSummaryOut]
    total: int


class OrderAttributionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str | None = None
    campaign: str | None = None
    ref: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None


class AdminOrderDetailOut(AdminOrderSummaryOut):
    #: Nguồn của LẦN ĐẶT (last-touch) và nguồn ĐẦU TIÊN của khách (first-touch).
    attribution: OrderAttributionOut
    customer_first_touch: OrderAttributionOut | None = None
    subtotal: Decimal
    shipping_fee: Decimal
    discount_total: Decimal
    customer_note: str | None
    items_detail: list[OrderItemOut]
    shipping: AdminShippingOut
    events: list[OrderStatusEventOut]
    allowed_transitions: list[str]


class OrderStatusChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_status: str = Field(min_length=1, max_length=20)
    reason: str | None = Field(default=None, max_length=300)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return _optional_text(value)


# ============================================================================
# G17 — THANH TOÁN (quản trị). Thiết kế: `docs/payments.md`.
# ============================================================================
class PaymentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    event_type: str
    from_status: str | None
    to_status: str | None
    amount: Decimal | None
    currency: str | None
    outcome: str
    reason: str | None
    actor: str
    created_at: datetime


class AdminPaymentOut(BaseModel):
    payment_id: uuid.UUID
    order_id: uuid.UUID
    order_number: str
    method: str
    status: str
    amount: Decimal
    currency: str
    provider_reference: str | None
    confirmed_by: str | None
    confirmed_at: datetime | None
    created_at: datetime
    allowed_actions: list[str]
    events: list[PaymentEventOut] = []


class AdminPaymentPageOut(BaseModel):
    items: list[AdminPaymentOut]
    total: int


class PaymentActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=200)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return _optional_text(value)


# ============================================================================
# KHO (quản trị). Thiết kế: `docs/inventory.md`. Con số tồn CHỈ có ở đây —
# đường công khai chỉ thấy nhãn Còn/Hết hàng.
# ============================================================================
class InventoryBalanceOut(BaseModel):
    sku: str
    product_name: str
    variant_name: str
    stock_tracking: bool
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int
    updated_at: datetime | None = None


class InventoryMovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    movement_type: str
    delta_on_hand: int
    delta_reserved: int
    order_number: str | None = None
    actor: str
    reason: str | None
    created_at: datetime


class InventoryDetailOut(BaseModel):
    balance: InventoryBalanceOut
    movements: list[InventoryMovementOut]


class InventoryMovementCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    movement_type: Literal["OPENING", "RECEIPT", "ADJUSTMENT", "RETURN"]
    #: Dương cho OPENING/RECEIPT/RETURN; ADJUSTMENT có thể âm (kiểm kê thiếu).
    quantity: int = Field(ge=-100_000, le=100_000)
    reason: str | None = Field(default=None, max_length=300)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return _optional_text(value)


class PriceHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_price: Decimal | None
    new_price: Decimal
    currency: str
    changed_by: str
    changed_at: datetime
    reason: str | None


class ProductImagePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alt_text: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = Field(default=None, ge=0, le=1000)
    is_primary: bool | None = None

    @field_validator("alt_text")
    @classmethod
    def _alt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _required_text(value, "Mô tả ảnh (alt)")


class AttributionReportRow(BaseModel):
    #: Giá trị của chiều nhóm; `None` = không có nguồn (truy cập trực tiếp).
    key: str | None
    customers: int
    orders: int
    revenue: Decimal
    paid_revenue: Decimal


class AttributionReportOut(BaseModel):
    model: str
    dimension: str
    rows: list[AttributionReportRow]
