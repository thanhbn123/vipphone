"""Mô hình dữ liệu VIP PHONE.

Schema thật do Alembic tạo (xem `migrations/`). KHÔNG gọi `create_all()`
ở môi trường thật — xem ADR-0001 §3.2.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
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
    #: Địa chỉ nhận hàng — MỘT ô tự do (anh chốt gọn lại 1 ô).
    #: ⚠️ API đơn vị vận chuyển cần Tỉnh/Huyện/Xã RIÊNG, nên khi nối lên đơn tự
    #: động sẽ phải TÁCH địa chỉ. Xem `migrations/0005` và MASTER_STATUS.
    address: Mapped[str | None] = mapped_column(String(300))
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

    #: G13 — khách hàng sở hữu vết lead này. NULLABLE vì lead cũ được backfill dần
    #: và vì liên kết là việc PHỤ: lỗi liên kết KHÔNG được làm hỏng việc tạo lead.
    customer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )

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


class CustomerStatus(StrEnum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    MERGED = "MERGED"


class Customer(Base):
    """Danh tính thương mại lâu dài. Xem `docs/adr/0002-customer-identity.md`.

    `phone_normalized` UNIQUE ở TẦNG DB — ràng buộc chỉ ở tầng ứng dụng thì hai
    request đồng thời vẫn tạo được hai khách (§ADR-0002 §2.1).
    """

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("customer_id", name="uq_customers_customer_id"),
        UniqueConstraint("phone_normalized", name="uq_customers_phone_normalized"),
        CheckConstraint("status IN ('ACTIVE','BLOCKED','MERGED')", name="ck_customers_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone_normalized: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    company_name: Mapped[str | None] = mapped_column(String(120))
    bni_chapter: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ACTIVE")
    marketing_consent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    consent_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CustomerDevice(Base):
    """Máy khách đang dùng. ĐÚNG MỘT `is_primary` mỗi khách (partial unique index).

    `model_code` có thể NULL: `leads.iphone_model` lưu TÊN HIỂN THỊ nên có dòng
    không tra được sang `iphone_models.display_name` (ADR-0002 §2.4).
    """

    __tablename__ = "customer_devices"
    __table_args__ = (
        UniqueConstraint("customer_id", "model_code", name="uq_customer_devices_customer_model"),
        Index(
            "uq_customer_devices_one_primary",
            "customer_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    brand: Mapped[str] = mapped_column(String(40), nullable=False, server_default="Apple")
    model_code: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    year: Mapped[int | None] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(String(40))
    storage: Mapped[str | None] = mapped_column(String(20))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CustomerAcquisition(Base):
    """FIRST-TOUCH: một dòng mỗi khách, ghi lần đầu, lead sau KHÔNG ghi đè.

    Giá trị của nó nằm ở chỗ là nguồn gốc — ghi đè là làm mất đúng thứ đang cần.
    """

    __tablename__ = "customer_acquisition"
    __table_args__ = (UniqueConstraint("customer_id", name="uq_customer_acquisition_customer"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str | None] = mapped_column(String(32))
    referrer_name: Mapped[str | None] = mapped_column(String(120))
    ref: Mapped[str | None] = mapped_column(String(64))
    utm_source: Mapped[str | None] = mapped_column(String(64))
    utm_medium: Mapped[str | None] = mapped_column(String(64))
    utm_campaign: Mapped[str | None] = mapped_column(String(64))
    utm_content: Mapped[str | None] = mapped_column(String(64))
    first_gift_code: Mapped[str | None] = mapped_column(String(32))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ============================================================================
# G14 — DANH MỤC SẢN PHẨM. Thiết kế: `docs/catalog.md`.
#
# LUẬT TIỀN (không có ngoại lệ): mọi cột tiền là `Numeric(12, 2)` / `Decimal`.
# KHÔNG dùng `Float`. `float` là số nhị phân nên `0.1 + 0.2 != 0.3`; giá đã ghi
# vào đơn hàng là thứ không migration nào vá lại được.
# ============================================================================


class CompatibilityType(StrEnum):
    """Mức tương thích. `PARTIAL` tồn tại vì thực tế phụ kiện không nhị phân."""

    FULL = "FULL"
    PARTIAL = "PARTIAL"
    CASE_FIT = "CASE_FIT"


COMPATIBILITY_TYPE_VALUES = tuple(t.value for t in CompatibilityType)


class Category(Base):
    """Nhóm hàng. `code` là TỪ VỰNG ổn định (slug chữ HOA), UNIQUE ở tầng DB."""

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("code", name="uq_categories_code"),
        CheckConstraint("code = upper(code)", name="ck_categories_code_upper"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Product(Base):
    """Sản phẩm. `product_id` UUID là định danh CÔNG KHAI; `id` là khoá nội bộ."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_products_product_id"),
        UniqueConstraint("slug", name="uq_products_slug"),
        Index("ix_products_category_active", "category_id", "active"),
        Index("ix_products_active_name", "active", "name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(80))
    #: RESTRICT: xoá category còn sản phẩm là phá dữ liệu. Muốn ẩn ⇒ `active = false`.
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProductVariant(Base):
    """SKU — thứ thật sự bán được.

    `cost_price` là giá NHẬP: dữ liệu nội bộ, KHÔNG BAO GIỜ trả ra API công khai
    (lộ giá nhập = lộ biên lợi nhuận). Có test khẳng định JSON công khai không
    chứa khoá này.

    `stock_tracking` chỉ là CỜ: G14 chưa có inventory engine, cột này KHÔNG sinh
    ra số lượng tồn kho nào. Đừng đọc nó thành "đang có hàng".
    """

    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_product_variants_sku"),
        Index("ix_product_variants_product_active", "product_id", "active"),
        CheckConstraint("sale_price >= 0", name="ck_product_variants_sale_price_non_negative"),
        CheckConstraint(
            "cost_price IS NULL OR cost_price >= 0",
            name="ck_product_variants_cost_price_non_negative",
        ),
        CheckConstraint(
            "compare_at_price IS NULL OR compare_at_price >= sale_price",
            name="ck_product_variants_compare_at_not_below_sale",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_product_variants_currency_format"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    variant_name: Mapped[str] = mapped_column(String(120), nullable=False)
    color: Mapped[str | None] = mapped_column(String(40))
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sale_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    compare_at_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="VND")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    stock_tracking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DeviceCompatibility(Base):
    """SKU này dùng được cho máy nào.

    Trỏ tới **SKU**, không trỏ tới product: hai SKU của cùng một product có thể
    tương thích khác nhau (ốp iPhone 15 không vừa iPhone 16). Gắn vào product là
    ép một sự thật sai — và sai theo hướng khách mua nhầm.

    `device_model_code` khớp `iphone_models.model_code` (MÃ), không khớp
    `display_name` (tên hiển thị — không UNIQUE, xem `docs/adr/0002` §2.4).
    Cố ý KHÔNG có FK cứng: xem `docs/catalog.md` §3.6 (kèm rủi ro đã ghi).
    """

    __tablename__ = "device_compatibility"
    __table_args__ = (
        UniqueConstraint(
            "sku_id", "device_brand", "device_model_code", name="uq_device_compatibility_sku_device"
        ),
        Index("ix_device_compatibility_lookup", "device_brand", "device_model_code"),
        CheckConstraint(
            "compatibility_type IN ('FULL','PARTIAL','CASE_FIT')",
            name="ck_device_compatibility_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    sku_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False
    )
    device_brand: Mapped[str] = mapped_column(String(40), nullable=False, server_default="Apple")
    device_model_code: Mapped[str] = mapped_column(String(64), nullable=False)
    compatibility_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RecommendationCategoryPriority(Base):
    """G15 — thứ tự ưu tiên NHÓM HÀNG khi gợi ý, theo ngữ cảnh.

    Thứ tự là DỮ LIỆU: đổi bằng `UPDATE`, không cần deploy. UNIQUE (context,
    priority) ở tầng DB vì hai nhóm cùng hạng làm thứ tự gợi ý KHÔNG xác định.
    Xem `docs/recommendation-engine.md`.
    """

    __tablename__ = "recommendation_category_priority"
    __table_args__ = (
        UniqueConstraint("context", "category_code", name="uq_reco_priority_context_category"),
        UniqueConstraint("context", "priority", name="uq_reco_priority_context_priority"),
        CheckConstraint("priority > 0", name="ck_reco_priority_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    context: Mapped[str] = mapped_column(String(40), nullable=False)
    category_code: Mapped[str] = mapped_column(
        String(40),
        ForeignKey(
            "categories.code",
            name="fk_reco_priority_category_code",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


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


# ============================================================================
# G16 — GIỎ HÀNG + ĐƠN HÀNG. Thiết kế: `docs/commerce.md`.
#
# MÁY CHỦ GIỮ GIÁ: tổng tiền do máy chủ tính từ giá SKU hiện hành lúc đặt, rồi
# CHỤP vào `order_items.unit_price`. Không có đường nào nhận tổng tiền từ client.
# ============================================================================


class CartStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CHECKED_OUT = "CHECKED_OUT"
    ABANDONED = "ABANDONED"


class OrderStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    CONFIRMED = "CONFIRMED"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PaymentStatus(StrEnum):
    UNPAID = "UNPAID"
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class Cart(Base):
    __tablename__ = "carts"
    __table_args__ = (
        UniqueConstraint("cart_id", name="uq_carts_cart_id"),
        CheckConstraint("status IN ('ACTIVE', 'CHECKED_OUT', 'ABANDONED')", name="ck_carts_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    cart_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    #: SHA-256 của token bí mật đưa cho trình duyệt. KHÔNG lưu token thô.
    owner_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ACTIVE")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="VND")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "sku_id", name="uq_cart_items_cart_sku"),
        CheckConstraint("quantity BETWEEN 1 AND 99", name="ck_cart_items_quantity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    cart_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    sku_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_orders_order_id"),
        UniqueConstraint("order_number", name="uq_orders_order_number"),
        UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),
        UniqueConstraint("cart_id", name="uq_orders_cart_id"),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_PAYMENT', 'CONFIRMED', 'PROCESSING', 'SHIPPED', "
            "'COMPLETED', 'CANCELLED')",
            name="ck_orders_status",
        ),
        CheckConstraint(
            "payment_status IN ('UNPAID', 'PENDING', 'PAID', 'FAILED', 'REFUNDED')",
            name="ck_orders_payment_status",
        ),
        CheckConstraint(
            "subtotal >= 0 AND shipping_fee >= 0 AND discount_total >= 0 AND grand_total >= 0",
            name="ck_orders_money_non_negative",
        ),
        CheckConstraint(
            "grand_total = subtotal + shipping_fee - discount_total",
            name="ck_orders_grand_total_formula",
        ),
        Index("ix_orders_status_created", "status", "created_at"),
        Index("ix_orders_customer", "customer_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    order_number: Mapped[str] = mapped_column(String(24), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    cart_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("carts.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    #: SHA-256 của nội dung yêu cầu checkout — dùng lại CÙNG khoá với nội dung KHÁC ⇒ 422.
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="UNPAID")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="VND")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_fee: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    discount_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    customer_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OrderItem(Base):
    """Dòng đơn — ẢNH CHỤP tên + giá lúc đặt. Đổi giá SKU sau đó không đụng tới đây."""

    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "sku_id", name="uq_order_items_order_sku"),
        CheckConstraint("quantity BETWEEN 1 AND 99", name="ck_order_items_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price"),
        CheckConstraint("line_total = unit_price * quantity", name="ck_order_items_line_total"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    sku_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(160), nullable=False)
    variant_name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ShippingAddress(Base):
    __tablename__ = "shipping_addresses"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_shipping_addresses_order"),
        CheckConstraint("phone ~ '^0[35789][0-9]{8}$'", name="ck_shipping_addresses_phone"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    recipient_name: Mapped[str] = mapped_column(String(80), nullable=False)
    phone: Mapped[str] = mapped_column(String(16), nullable=False)
    address_line: Mapped[str] = mapped_column(String(300), nullable=False)
    ward: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(80))
    province: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OrderStatusEvent(Base):
    """Vết chuyển trạng thái đơn (cả `status` lẫn `payment_status`). Không chứa PII."""

    __tablename__ = "order_status_events"
    __table_args__ = (
        CheckConstraint(
            "field IN ('status','payment_status')", name="ck_order_status_events_field"
        ),
        Index("ix_order_status_events_order", "order_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    field: Mapped[str] = mapped_column(String(20), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(20))
    to_value: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "ACTIVE_GIFT_STATUSES",
    "COMPATIBILITY_TYPE_VALUES",
    "GIFT_STATUS_VALUES",
    "AuditEvent",
    "AuditEventType",
    "Base",
    "Cart",
    "CartItem",
    "CartStatus",
    "Category",
    "CompatibilityType",
    "Customer",
    "CustomerAcquisition",
    "CustomerDevice",
    "DeviceCompatibility",
    "GiftStatus",
    "IphoneModel",
    "Lead",
    "Order",
    "OrderItem",
    "OrderStatus",
    "OrderStatusEvent",
    "PaymentStatus",
    "Product",
    "ProductVariant",
    "RecommendationCategoryPriority",
    "ShippingAddress",
    "Text",
]
