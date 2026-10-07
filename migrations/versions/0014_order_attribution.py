"""Attribution: nguồn của ĐƠN (last-touch lúc đặt) + bổ sung FIRST-TOUCH của khách.

Thiết kế: `docs/attribution.md`.

1. ADDITIVE: chỉ thêm cột NULLABLE. Không xoá/đổi cột cũ.
2. `orders.*` (source, campaign, ref, utm_*) = nguồn của LẦN ĐẶT NÀY — chụp lúc
   checkout, không đổi về sau.
3. `customer_acquisition` = FIRST-TOUCH, đã có từ G13. Bổ sung:
   - `campaign` (lead có cột này nhưng G13 chưa chép sang) — BACKFILL từ chính lead
     đầu tiên (`first_gift_code`), chỉ khi đang NULL ⇒ không ghi đè gì.
   - `acquired_via` ('LEAD' | 'ORDER') và `first_order_id`: khách đến thẳng cửa hàng
     (chưa từng để lại lead) thì first-touch lấy từ đơn đầu tiên.

Revision ID: 0014_order_attribution
Revises: 0013_product_images
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_order_attribution"
down_revision: str | None = "0013_product_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORDER_COLUMNS = (
    ("source", 32),
    ("campaign", 64),
    ("ref", 64),
    ("utm_source", 64),
    ("utm_medium", 64),
    ("utm_campaign", 64),
    ("utm_content", 64),
)


def upgrade() -> None:
    for name, length in ORDER_COLUMNS:
        op.add_column("orders", sa.Column(name, sa.String(length=length), nullable=True))
    op.create_index("ix_orders_source", "orders", ["source"])
    op.create_index("ix_orders_utm_campaign", "orders", ["utm_campaign"])
    op.create_index("ix_orders_ref", "orders", ["ref"])

    op.add_column(
        "customer_acquisition", sa.Column("campaign", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "customer_acquisition",
        sa.Column("acquired_via", sa.String(length=10), nullable=False, server_default="LEAD"),
    )
    op.add_column(
        "customer_acquisition",
        sa.Column(
            "first_order_id",
            sa.BigInteger(),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_customer_acquisition_via",
        "customer_acquisition",
        "acquired_via IN ('LEAD', 'ORDER')",
    )
    # Backfill campaign từ CHÍNH lead đầu tiên — chỉ điền khi đang trống.
    op.execute(
        "UPDATE customer_acquisition ca SET campaign = l.campaign "
        "FROM leads l WHERE l.gift_code = ca.first_gift_code "
        "AND ca.campaign IS NULL AND l.campaign IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_constraint("ck_customer_acquisition_via", "customer_acquisition", type_="check")
    op.drop_column("customer_acquisition", "first_order_id")
    op.drop_column("customer_acquisition", "acquired_via")
    op.drop_column("customer_acquisition", "campaign")
    op.drop_index("ix_orders_ref", table_name="orders")
    op.drop_index("ix_orders_utm_campaign", table_name="orders")
    op.drop_index("ix_orders_source", table_name="orders")
    for name, _ in reversed(ORDER_COLUMNS):
        op.drop_column("orders", name)
