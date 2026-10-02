"""Gộp 4 cột địa chỉ thành MỘT cột `address`. Bỏ ô Chapter BNI khỏi form.

VÌ SAO GỘP: anh chốt địa chỉ gọn vào 1 ô. Đây là đánh đổi CÓ THẬT: API của đơn vị
vận chuyển (Viettel Post) nhận PROVINCE/DISTRICT/WARD/ADDRESS RIÊNG, nên khi nối
lên đơn tự động sẽ phải TÁCH địa chỉ — bằng tay, hoặc bằng một bước tách tự động.
Ghi ra đây để sau này không ai ngạc nhiên.

KHÔNG MẤT DỮ LIỆU: trước khi xoá 4 cột cũ, migration này GHÉP chúng vào `address`
cho mọi dòng đang có dữ liệu. Dòng nào đã có `address` thì giữ nguyên.

`bni_chapter` KHÔNG bị xoá — chỉ bỏ ô nhập trên form. Cột giữ nguyên để dữ liệu cũ
của lead đã nhập vẫn tra và xuất được (cùng cách đã làm với `company_name`).

Revision ID: 0005_single_address
Revises: 0004_case_color_optional
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005_single_address"
down_revision: str | None = "0004_case_color_optional"
branch_labels = None
depends_on = None

_OLD = ("address_street", "address_ward", "address_district", "address_province")


def upgrade() -> None:
    op.add_column("leads", sa.Column("address", sa.String(length=300), nullable=True))

    # Ghép 4 cột cũ vào cột mới TRƯỚC khi xoá — để không mất dữ liệu đã có.
    joined = ", ".join(f"NULLIF({c}, '')" for c in _OLD)
    has_any = " OR ".join(f"{c} IS NOT NULL" for c in _OLD)
    op.execute(
        f"UPDATE leads SET address = concat_ws(', ', {joined}) "
        f"WHERE address IS NULL AND ({has_any})"
    )

    for column in _OLD:
        op.drop_column("leads", column)


def downgrade() -> None:
    op.add_column("leads", sa.Column("address_street", sa.String(length=200), nullable=True))
    op.add_column("leads", sa.Column("address_ward", sa.String(length=120), nullable=True))
    op.add_column("leads", sa.Column("address_district", sa.String(length=120), nullable=True))
    op.add_column("leads", sa.Column("address_province", sa.String(length=120), nullable=True))
    # Không thể tách ngược một cách đáng tin — đưa toàn bộ vào `address_street`
    # và GHI RÕ như vậy, thay vì đoán rồi chia sai.
    op.execute("UPDATE leads SET address_street = address WHERE address IS NOT NULL")
    op.drop_column("leads", "address")
