"""`case_color` cho phép rỗng — đổi ô chọn màu thành ô GHI CHÚ màu mong muốn.

VÌ SAO: trước đây khách phải chọn từ danh sách cố định (Đen/Trắng/Trong suốt/Xanh/
Hồng/Khác). Nay thay bằng ô ghi chú tự do, nên KHÔNG thể bắt buộc — có khách chỉ ghi
"màu gì cũng được" hoặc bỏ trống và để nhân viên gọi hỏi.

VÌ SAO PHẢI MIGRATION: cột đang `NOT NULL`. Ô trống gửi lên `NULL` (theo đúng quy ước
đã dùng ở UI-2: ô trống ⇒ NULL, không lưu chuỗi rỗng), nên `NOT NULL` sẽ chặn.

Tương lai: khi có ẢNH MẪU để khách chọn, giá trị chọn vẫn ghi vào CHÍNH cột này —
không cần thêm cột mới, và dữ liệu cũ vẫn nằm cùng một chỗ.

Revision ID: 0004_case_color_optional
Revises: 0003_contact_address
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004_case_color_optional"
down_revision: str | None = "0003_contact_address"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("leads", "case_color", existing_type=sa.String(length=40), nullable=True)


def downgrade() -> None:
    # Điền giá trị cho các dòng đang NULL trước khi siết lại NOT NULL, nếu không
    # downgrade sẽ hỏng ngay khi có dữ liệu. "Khác" là giá trị hợp lệ cũ.
    op.execute("UPDATE leads SET case_color = 'Khác' WHERE case_color IS NULL")
    op.alter_column("leads", "case_color", existing_type=sa.String(length=40), nullable=False)
