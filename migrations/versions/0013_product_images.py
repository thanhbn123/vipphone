"""Ảnh sản phẩm: `product_images`. Thiết kế: `docs/product-images.md`.

1. ADDITIVE.
2. DB giữ `storage_key` (khoá trong kho lưu), KHÔNG giữ URL ngoài ⇒ không có cách
   nào khai một ảnh hotlink từ trang khác.
3. `alt_text` BẮT BUỘC (trợ năng + SEO).
4. Tối đa MỘT ảnh chính mỗi sản phẩm (partial unique index).

Revision ID: 0013_product_images
Revises: 0012_price_history
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0013_product_images"
down_revision: str | None = "0012_price_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_images",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("image_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column(
            "product_id",
            sa.BigInteger(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(length=120), nullable=False),
        sa.Column("content_type", sa.String(length=20), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("alt_text", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("image_id", name="uq_product_images_image_id"),
        sa.UniqueConstraint("storage_key", name="uq_product_images_storage_key"),
        sa.CheckConstraint(
            "content_type IN ('image/png', 'image/jpeg', 'image/webp')",
            name="ck_product_images_content_type",
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_product_images_byte_size"),
        sa.CheckConstraint("length(trim(alt_text)) > 0", name="ck_product_images_alt_text"),
    )
    op.create_index("ix_product_images_product", "product_images", ["product_id", "sort_order"])
    op.create_index(
        "uq_product_images_one_primary",
        "product_images",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def downgrade() -> None:
    op.drop_index("uq_product_images_one_primary", table_name="product_images")
    op.drop_index("ix_product_images_product", table_name="product_images")
    op.drop_table("product_images")
