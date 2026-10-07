"""Kho tối giản: `inventory_balances` + `inventory_movements`. Thiết kế: `docs/inventory.md`.

Điều migration này PHẢI giữ:

1. ADDITIVE. Một kho (không đa kho — nghiệp vụ hiện tại không cần).
2. `quantity_available` là CỘT SINH (`on_hand - reserved`, STORED) — không thể
   lệch khỏi công thức vì không ai ghi được vào nó.
3. Bất biến ở TẦNG DB: `on_hand >= 0`, `reserved >= 0`, `reserved <= on_hand`.
   Một lỗi ở tầng ứng dụng không thể làm kho âm hay giữ quá số đang có.
4. `inventory_movements` là SỔ CÁI chỉ-thêm: mọi thay đổi số dư có đúng một dòng,
   kèm người làm + lý do. Số dư = tổng các dòng (có test đối chiếu).
5. Chỉ SKU bật `product_variants.stock_tracking` mới bị giữ/kiểm tồn khi đặt.

Revision ID: 0011_inventory
Revises: 0010_payments
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_inventory"
down_revision: str | None = "0010_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MOVEMENT_TYPES = ("OPENING", "RECEIPT", "RESERVE", "RELEASE", "SALE", "ADJUSTMENT", "RETURN")


def upgrade() -> None:
    op.create_table(
        "inventory_balances",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "sku_id",
            sa.BigInteger(),
            sa.ForeignKey("product_variants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity_on_hand", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quantity_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "quantity_available",
            sa.Integer(),
            sa.Computed("quantity_on_hand - quantity_reserved", persisted=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("sku_id", name="uq_inventory_balances_sku"),
        sa.CheckConstraint("quantity_on_hand >= 0", name="ck_inventory_on_hand_non_negative"),
        sa.CheckConstraint("quantity_reserved >= 0", name="ck_inventory_reserved_non_negative"),
        sa.CheckConstraint(
            "quantity_reserved <= quantity_on_hand", name="ck_inventory_reserved_le_on_hand"
        ),
    )

    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "sku_id",
            sa.BigInteger(),
            sa.ForeignKey("product_variants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column("delta_on_hand", sa.Integer(), nullable=False),
        sa.Column("delta_reserved", sa.Integer(), nullable=False),
        sa.Column(
            "order_id",
            sa.BigInteger(),
            sa.ForeignKey("orders.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "movement_type IN ('OPENING', 'RECEIPT', 'RESERVE', 'RELEASE', 'SALE', "
            "'ADJUSTMENT', 'RETURN')",
            name="ck_inventory_movements_type",
        ),
        sa.CheckConstraint(
            "delta_on_hand <> 0 OR delta_reserved <> 0", name="ck_inventory_movements_not_empty"
        ),
    )
    op.create_index("ix_inventory_movements_sku", "inventory_movements", ["sku_id", "id"])
    op.create_index("ix_inventory_movements_order", "inventory_movements", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_inventory_movements_order", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_sku", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_table("inventory_balances")
