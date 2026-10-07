"""G17 — Nền tảng thanh toán độc lập nhà cung cấp: `payments`, `payment_events`.

Thiết kế: `docs/payments.md`. Điều migration này PHẢI giữ:

1. ADDITIVE — chỉ `CREATE TABLE`/`CREATE INDEX`.
2. `payments.amount` là `Numeric(12,2)`, chụp từ `orders.grand_total` lúc tạo.
   Webhook báo số tiền KHÁC ⇒ bị từ chối, không "làm tròn cho khớp".
3. Mỗi đơn có TỐI ĐA MỘT payment đang mở/đã trả (partial unique index trên
   `order_id` với status CREATED/PENDING/PAID) ⇒ không thể có hai khoản thu cho
   một đơn.
4. CHỐNG XỬ LÝ TRÙNG webhook ở tầng DB: UNIQUE (provider, provider_event_id).
5. KHÔNG lưu payload thô, chữ ký hay dữ liệu thẻ/tài khoản. `payment_events` chỉ
   giữ trường đã kiểm (số tiền, tiền tệ, trạng thái) + băm payload để đối chiếu.

Revision ID: 0010_payments
Revises: 0009_cart_order
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0010_payments"
down_revision: str | None = "0009_cart_order"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAYMENT_METHODS = ("COD", "BANK_TRANSFER_MANUAL", "STAGING_MOCK")
PAYMENT_STATES = ("CREATED", "PENDING", "PAID", "FAILED", "CANCELLED", "REFUNDED")
EVENT_OUTCOMES = ("APPLIED", "DUPLICATE", "REJECTED")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("payment_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column(
            "order_id",
            sa.BigInteger(),
            sa.ForeignKey("orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("provider_reference", sa.String(length=64), nullable=True),
        sa.Column("confirmed_by", sa.String(length=80), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("payment_id", name="uq_payments_payment_id"),
        sa.UniqueConstraint("provider_reference", name="uq_payments_provider_reference"),
        sa.CheckConstraint(_in("method", PAYMENT_METHODS), name="ck_payments_method"),
        sa.CheckConstraint(_in("status", PAYMENT_STATES), name="ck_payments_status"),
        sa.CheckConstraint("amount >= 0", name="ck_payments_amount_non_negative"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_payments_currency_format"),
    )
    op.create_index(
        "uq_payments_one_open_per_order",
        "payments",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('CREATED','PENDING','PAID')"),
    )
    op.create_index("ix_payments_status_created", "payments", ["status", "created_at"])

    op.create_table(
        "payment_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "payment_id",
            sa.BigInteger(),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=True),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_payment_events_provider_event"
        ),
        sa.CheckConstraint(_in("outcome", EVENT_OUTCOMES), name="ck_payment_events_outcome"),
    )
    op.create_index("ix_payment_events_payment", "payment_events", ["payment_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_payment_events_payment", table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_index("ix_payments_status_created", table_name="payments")
    op.drop_index("uq_payments_one_open_per_order", table_name="payments")
    op.drop_table("payments")
