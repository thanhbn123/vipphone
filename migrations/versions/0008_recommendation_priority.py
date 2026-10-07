"""G15 — `recommendation_category_priority`: thứ tự ưu tiên nhóm hàng khi gợi ý.

Thiết kế: `docs/recommendation-engine.md`. Điều migration này PHẢI giữ:

1. ADDITIVE — chỉ `CREATE TABLE` + seed. Không sửa `0001`..`0007`.
2. Thứ tự ưu tiên là DỮ LIỆU, không phải mã: đổi thứ tự = `UPDATE`, không deploy.
3. UNIQUE (context, category_code) và UNIQUE (context, priority) ở TẦNG DB: hai
   nhóm cùng hạng thì thứ tự gợi ý phụ thuộc vào thứ tự đọc đĩa của PostgreSQL —
   tức là KHÔNG xác định. Chặn ở DB để không phụ thuộc vào việc người sửa nhớ.
4. `category_code` có FK tới `categories.code` (ON UPDATE CASCADE): gõ sai mã
   nhóm thì INSERT bị từ chối thay vì âm thầm không bao giờ khớp.
5. `CASE` CỐ Ý KHÔNG có trong context `POST_GIFT`: khách vừa nhận ốp miễn phí,
   gợi ý lại ốp là gợi ý thứ họ vừa có.

Revision ID: 0008_recommendation_priority
Revises: 0007_product_catalog
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_recommendation_priority"
down_revision: str | None = "0007_product_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Ngữ cảnh gợi ý sau khi khách nhận ốp miễn phí.
POST_GIFT_CONTEXT = "POST_GIFT"

#: Thứ tự ưu tiên đã duyệt (issue #63). Vị trí trong danh sách = `priority` (1..7).
POST_GIFT_PRIORITY: list[str] = [
    "SCREEN_PROTECTOR",
    "CHARGER",
    "CABLE",
    "MAGSAFE",
    "POWER_BANK",
    "EARPHONE",
    "CAR_ACCESSORY",
]


def seed_rows() -> list[dict]:
    """Dùng CHUNG cho migration và test — một nguồn duy nhất."""
    return [
        {"context": POST_GIFT_CONTEXT, "category_code": code, "priority": index + 1}
        for index, code in enumerate(POST_GIFT_PRIORITY)
    ]


def upgrade() -> None:
    table = op.create_table(
        "recommendation_category_priority",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("context", sa.String(length=40), nullable=False),
        sa.Column("category_code", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["category_code"],
            ["categories.code"],
            name="fk_reco_priority_category_code",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("context", "category_code", name="uq_reco_priority_context_category"),
        sa.UniqueConstraint("context", "priority", name="uq_reco_priority_context_priority"),
        sa.CheckConstraint("priority > 0", name="ck_reco_priority_positive"),
    )
    op.bulk_insert(table, seed_rows())


def downgrade() -> None:
    op.drop_table("recommendation_category_priority")
