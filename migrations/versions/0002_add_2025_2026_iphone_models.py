"""Thêm iPhone 17 (2025) và iPhone 18 (2026) vào danh mục.

VÌ SAO CẦN MIGRATION RIÊNG: `0001_initial` đã chạy trên staging rồi, nên sửa
`SEED_MODELS` trong 0001 **không** làm database đang chạy có thêm dòng nào. Migration
này lo phần đó.

VÌ SAO PHẢI TÍNH LẠI `sort_order` CHO CẢ BẢNG: `seed_rows()` tính
`sort_order = (năm_mới_nhất - year) * 100 + index`. Khi thêm 2026, "năm mới nhất"
đổi từ 2024 thành 2026 ⇒ mọi giá trị cũ lệch chuẩn. Nếu chỉ chèn dòng mới thì
2026 sẽ có sort_order 0 — **trùng** với 2024 (cũng 0) và landing xếp sai thứ tự.
Nên migration này chèn dòng mới RỒI đánh số lại toàn bộ.

Revision ID: 0002_iphone_2025_2026
Revises: 0001_initial
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002_iphone_2025_2026"
down_revision: str | None = "0001_initial"
branch_labels = None
depends_on = None

#: Năm mới nhất SAU migration này — dùng cho công thức sort_order.
NEWEST_YEAR = 2026

NEW_MODELS: list[tuple[int, str, str]] = [
    (2025, "iphone-17", "iPhone 17"),
    (2025, "iphone-17-air", "iPhone 17 Air"),
    (2025, "iphone-17-pro", "iPhone 17 Pro"),
    (2025, "iphone-17-pro-max", "iPhone 17 Pro Max"),
    (2026, "iphone-18-pro", "iPhone 18 Pro"),
    (2026, "iphone-18-pro-max", "iPhone 18 Pro Max"),
    (2026, "iphone-duo", "iPhone Duo"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for year, code, name in NEW_MODELS:
        conn.execute(
            sa.text(
                "INSERT INTO iphone_models (year, model_code, display_name, active, sort_order) "
                "VALUES (:y, :c, :n, true, 0) "
                "ON CONFLICT (model_code) DO NOTHING"
            ),
            {"y": year, "c": code, "n": name},
        )

    # Đánh số lại TOÀN BỘ theo công thức của `seed_rows()`, giữ nguyên thứ tự
    # tương đối trong mỗi năm (dòng cũ đang có sort_order tăng dần).
    conn.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT id, year,
                       ROW_NUMBER() OVER (PARTITION BY year ORDER BY sort_order, model_code) - 1 AS idx
                FROM iphone_models
            )
            UPDATE iphone_models m
            SET sort_order = (:newest - o.year) * 100 + o.idx
            FROM ordered o
            WHERE m.id = o.id
            """
        ),
        {"newest": NEWEST_YEAR},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM iphone_models WHERE model_code = ANY(:codes)"),
        {"codes": [c for _, c, _ in NEW_MODELS]},
    )
    # Trả lại cách đánh số cũ (năm mới nhất là 2024).
    conn.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT id, year,
                       ROW_NUMBER() OVER (PARTITION BY year ORDER BY sort_order, model_code) - 1 AS idx
                FROM iphone_models
            )
            UPDATE iphone_models m
            SET sort_order = (2024 - o.year) * 100 + o.idx
            FROM ordered o
            WHERE m.id = o.id
            """
        )
    )
