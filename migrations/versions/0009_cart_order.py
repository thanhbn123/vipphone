"""G16 — Giỏ hàng + đơn hàng: `carts`, `cart_items`, `orders`, `order_items`,
`shipping_addresses`, `order_status_events`.

Thiết kế: `docs/commerce.md`. Điều migration này PHẢI giữ:

1. ADDITIVE — chỉ `CREATE TABLE`. Không sửa `0001`..`0008`.
2. TIỀN `Numeric(12,2)` ở MỌI cột tiền. Không `float`.
3. MÁY CHỦ GIỮ GIÁ: `order_items.unit_price` là ẢNH CHỤP giá lúc đặt. Đổi giá SKU
   sau đó KHÔNG được đổi đơn cũ — nên giá nằm ở dòng đơn, không tham chiếu sống.
4. IDEMPOTENT Ở TẦNG DB:
   - `orders.idempotency_key` UNIQUE — gửi lại cùng khoá ⇒ cùng một đơn.
   - `orders.cart_id` UNIQUE — một giỏ chỉ sinh ĐÚNG MỘT đơn, kể cả khi hai lần
     checkout đồng thời mang HAI khoá khác nhau.
5. QUYỀN SỞ HỮU: giỏ và đơn giữ `owner_token_hash` (SHA-256 của token bí mật đưa
   cho trình duyệt). Máy chủ KHÔNG lưu token thô.
6. Trạng thái là TỪ VỰNG ĐÓNG (CHECK). Chuyển trạng thái hợp lệ do tầng dịch vụ
   quyết định và được ghi vết ở `order_status_events`.

Revision ID: 0009_cart_order
Revises: 0008_recommendation_priority
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0009_cart_order"
down_revision: str | None = "0008_recommendation_priority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CART_STATUSES = ("ACTIVE", "CHECKED_OUT", "ABANDONED")
ORDER_STATUSES = (
    "DRAFT",
    "PENDING_PAYMENT",
    "CONFIRMED",
    "PROCESSING",
    "SHIPPED",
    "COMPLETED",
    "CANCELLED",
)
PAYMENT_STATUSES = ("UNPAID", "PENDING", "PAID", "FAILED", "REFUNDED")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "carts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("cart_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("owner_token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="VND"),
        *_timestamps(),
        sa.UniqueConstraint("cart_id", name="uq_carts_cart_id"),
        sa.CheckConstraint(_in("status", CART_STATUSES), name="ck_carts_status"),
    )

    op.create_table(
        "cart_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "cart_id",
            sa.BigInteger(),
            sa.ForeignKey("carts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sku_id",
            sa.BigInteger(),
            sa.ForeignKey("product_variants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("cart_id", "sku_id", name="uq_cart_items_cart_sku"),
        sa.CheckConstraint("quantity BETWEEN 1 AND 99", name="ck_cart_items_quantity"),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("order_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("order_number", sa.String(length=24), nullable=False),
        sa.Column(
            "customer_id",
            sa.BigInteger(),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "cart_id",
            sa.BigInteger(),
            sa.ForeignKey("carts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("owner_token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payment_status", sa.String(length=20), nullable=False, server_default="UNPAID"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="VND"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("shipping_fee", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("customer_note", sa.String(length=500), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("order_id", name="uq_orders_order_id"),
        sa.UniqueConstraint("order_number", name="uq_orders_order_number"),
        sa.UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),
        sa.UniqueConstraint("cart_id", name="uq_orders_cart_id"),
        sa.CheckConstraint(_in("status", ORDER_STATUSES), name="ck_orders_status"),
        sa.CheckConstraint(
            _in("payment_status", PAYMENT_STATUSES), name="ck_orders_payment_status"
        ),
        sa.CheckConstraint(
            "subtotal >= 0 AND shipping_fee >= 0 AND discount_total >= 0 AND grand_total >= 0",
            name="ck_orders_money_non_negative",
        ),
        sa.CheckConstraint(
            "grand_total = subtotal + shipping_fee - discount_total",
            name="ck_orders_grand_total_formula",
        ),
    )
    op.create_index("ix_orders_status_created", "orders", ["status", "created_at"])
    op.create_index("ix_orders_customer", "orders", ["customer_id"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "order_id",
            sa.BigInteger(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # RESTRICT: xoá SKU đã có trong đơn là xoá bằng chứng của một giao dịch.
        sa.Column(
            "sku_id",
            sa.BigInteger(),
            sa.ForeignKey("product_variants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=160), nullable=False),
        sa.Column("variant_name", sa.String(length=120), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("order_id", "sku_id", name="uq_order_items_order_sku"),
        sa.CheckConstraint("quantity BETWEEN 1 AND 99", name="ck_order_items_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price"),
        sa.CheckConstraint("line_total = unit_price * quantity", name="ck_order_items_line_total"),
    )

    op.create_table(
        "shipping_addresses",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "order_id",
            sa.BigInteger(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recipient_name", sa.String(length=80), nullable=False),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("address_line", sa.String(length=300), nullable=False),
        sa.Column("ward", sa.String(length=80), nullable=True),
        sa.Column("district", sa.String(length=80), nullable=True),
        sa.Column("province", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("order_id", name="uq_shipping_addresses_order"),
        sa.CheckConstraint("phone ~ '^0[35789][0-9]{8}$'", name="ck_shipping_addresses_phone"),
    )

    op.create_table(
        "order_status_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "order_id",
            sa.BigInteger(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field", sa.String(length=20), nullable=False),
        sa.Column("from_value", sa.String(length=20), nullable=True),
        sa.Column("to_value", sa.String(length=20), nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "field IN ('status','payment_status')", name="ck_order_status_events_field"
        ),
    )
    op.create_index("ix_order_status_events_order", "order_status_events", ["order_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_order_status_events_order", table_name="order_status_events")
    op.drop_table("order_status_events")
    op.drop_table("shipping_addresses")
    op.drop_table("order_items")
    op.drop_index("ix_orders_customer", table_name="orders")
    op.drop_index("ix_orders_status_created", table_name="orders")
    op.drop_table("orders")
    op.drop_table("cart_items")
    op.drop_table("carts")
