"""Lịch sử giá: `price_history` + trigger ghi TỰ ĐỘNG khi `sale_price` đổi.

Thiết kế: `docs/price-history.md`. Điều migration này PHẢI giữ:

1. ADDITIVE.
2. Ghi lịch sử bằng TRIGGER của PostgreSQL (`AFTER INSERT OR UPDATE OF sale_price`),
   không bằng mã ứng dụng. Lý do: đổi giá bằng bất kỳ đường nào — API, script,
   SQL tay — đều để lại vết, và vết nằm TRONG CÙNG giao dịch với lần đổi giá:
   đổi giá thất bại ⇒ rollback ⇒ không có dòng lịch sử nào. Không thể có giá đổi
   mà thiếu vết, cũng không thể có vết mà giá không đổi.
3. Người sửa + lý do đến từ biến phiên giao dịch (`set_config(..., is_local=true)`)
   do ứng dụng đặt. Không đặt (SQL tay) ⇒ người sửa = `db:<tên role>` — vẫn có vết.
4. Đơn cũ KHÔNG bị đụng: `order_items.unit_price` là ảnh chụp (G16).

Revision ID: 0012_price_history
Revises: 0011_inventory
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_price_history"
down_revision: str | None = "0011_inventory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION vipphone_record_price_change() RETURNS trigger AS $$
DECLARE
    v_actor  text := NULLIF(current_setting('vipphone.actor', true), '');
    v_reason text := NULLIF(current_setting('vipphone.price_reason', true), '');
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.sale_price IS NOT DISTINCT FROM OLD.sale_price THEN
        RETURN NEW;
    END IF;
    INSERT INTO price_history (sku_id, old_price, new_price, currency, changed_by, reason)
    VALUES (
        NEW.id,
        CASE WHEN TG_OP = 'UPDATE' THEN OLD.sale_price ELSE NULL END,
        NEW.sale_price,
        NEW.currency,
        COALESCE(v_actor, 'db:' || current_user),
        left(v_reason, 300)
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "price_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "sku_id",
            sa.BigInteger(),
            sa.ForeignKey("product_variants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("old_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("new_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("changed_by", sa.String(length=80), nullable=False),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.CheckConstraint("new_price >= 0", name="ck_price_history_new_price"),
    )
    op.create_index("ix_price_history_sku", "price_history", ["sku_id", "id"])

    op.execute(TRIGGER_FUNCTION)
    op.execute(
        "CREATE TRIGGER trg_product_variants_price_history "
        "AFTER INSERT OR UPDATE OF sale_price ON product_variants "
        "FOR EACH ROW EXECUTE FUNCTION vipphone_record_price_change()"
    )
    # SKU đã có trước migration: ghi một dòng "giá khởi điểm" để lịch sử không bắt
    # đầu từ khoảng trống. Người sửa ghi rõ là migration.
    op.execute(
        "INSERT INTO price_history (sku_id, old_price, new_price, currency, changed_by, reason) "
        "SELECT id, NULL, sale_price, currency, 'migration:0012', 'Giá tại thời điểm bật lịch sử' "
        "FROM product_variants"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_product_variants_price_history ON product_variants")
    op.execute("DROP FUNCTION IF EXISTS vipphone_record_price_change()")
    op.drop_index("ix_price_history_sku", table_name="price_history")
    op.drop_table("price_history")
