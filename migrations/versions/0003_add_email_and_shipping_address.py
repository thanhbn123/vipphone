"""Thêm Gmail + địa chỉ giao hàng (4 phần) vào `leads`.

VÌ SAO TÁCH 4 PHẦN: API của đơn vị vận chuyển (Viettel Post) nhận
PROVINCE / DISTRICT / WARD / ADDRESS RIÊNG, không nhận một chuỗi tự do. Gom vào một
ô thì lúc lên đơn tự động vẫn phải có người tách tay — mất đúng cái lợi cần có.

VÌ SAO KHÔNG hard-code danh mục tỉnh/phường: Việt Nam vừa sáp nhập đơn vị hành
chính, nên mọi danh sách chép tay đều có nguy cơ sai. Cột để dạng text; sau này nối
dropdown vào API của hãng vận chuyển (nguồn chuẩn của chính họ).

Tất cả NULLABLE: form phát ốp miễn phí tại quầy — bắt buộc điền địa chỉ sẽ làm rớt
khách. Muốn bắt buộc thì đổi ở tầng schema, không phải ở đây.

Revision ID: 0003_contact_address
Revises: 0002_iphone_2025_2026
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_contact_address"
down_revision: str | None = "0002_iphone_2025_2026"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("email", 254),
    ("address_street", 200),
    ("address_ward", 120),
    ("address_district", 120),
    ("address_province", 120),
)


def upgrade() -> None:
    for name, length in _COLUMNS:
        op.add_column("leads", sa.Column(name, sa.String(length=length), nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("leads", name)
