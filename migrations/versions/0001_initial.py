"""Khởi tạo schema VIP PHONE: leads, audit_events, iphone_models + seed danh mục.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-01

Ghi chú thiết kế quan trọng:

1. Schema CHỈ do migration tạo. Ứng dụng KHÔNG gọi `create_all()`.
2. `uq_leads_active_duplicate` là UNIQUE INDEX MỘT PHẦN trên
   `(phone, iphone_model)` với điều kiện `gift_status <> 'CANCELLED'`.
   Nhờ vậy chính sách chống trùng được ÉP Ở TẦNG DATABASE: hai request
   đồng thời cũng không tạo nổi hai gift cho cùng một khách.
3. Danh mục iPhone được SEED NGAY TRONG MIGRATION (dữ liệu nhúng, không đọc
   file ngoài) để migration luôn tái lập được kể cả khi `data/` đổi về sau.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Dữ liệu danh mục lấy ĐÚNG theo `data/iphone-models.json` tại baseline.
#: Không thêm model nào chưa được xác minh.
SEED_MODELS: list[tuple[int, str]] = [
    (2018, "iPhone XR"),
    (2018, "iPhone XS"),
    (2018, "iPhone XS Max"),
    (2019, "iPhone 11"),
    (2019, "iPhone 11 Pro"),
    (2019, "iPhone 11 Pro Max"),
    (2020, "iPhone SE (2020)"),
    (2020, "iPhone 12 mini"),
    (2020, "iPhone 12"),
    (2020, "iPhone 12 Pro"),
    (2020, "iPhone 12 Pro Max"),
    (2021, "iPhone 13 mini"),
    (2021, "iPhone 13"),
    (2021, "iPhone 13 Pro"),
    (2021, "iPhone 13 Pro Max"),
    (2022, "iPhone SE (2022)"),
    (2022, "iPhone 14"),
    (2022, "iPhone 14 Plus"),
    (2022, "iPhone 14 Pro"),
    (2022, "iPhone 14 Pro Max"),
    (2023, "iPhone 15"),
    (2023, "iPhone 15 Plus"),
    (2023, "iPhone 15 Pro"),
    (2023, "iPhone 15 Pro Max"),
    (2024, "iPhone 16"),
    (2024, "iPhone 16 Plus"),
    (2024, "iPhone 16 Pro"),
    (2024, "iPhone 16 Pro Max"),
]


def slugify_model(display_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
    return slug


#: Bảng tạm để `bulk_insert`, và cũng để test dựng lại danh mục.
MODELS_TABLE = sa.table(
    "iphone_models",
    sa.column("year", sa.Integer),
    sa.column("model_code", sa.String),
    sa.column("display_name", sa.String),
    sa.column("active", sa.Boolean),
    sa.column("sort_order", sa.Integer),
)


def seed_rows() -> list[dict]:
    """Sinh đúng các dòng seed của danh mục.

    Được `upgrade()` dùng để seed, VÀ được test dùng để dựng lại danh mục về
    trạng thái chuẩn sau mỗi test. Nhờ dùng CHUNG một hàm, dữ liệu seed và
    kỳ vọng của test không thể lệch nhau.
    """
    newest_year = max(year for year, _ in SEED_MODELS)
    per_year_counter: dict[int, int] = {}
    rows: list[dict] = []

    for year, display_name in SEED_MODELS:
        index_in_year = per_year_counter.get(year, 0)
        per_year_counter[year] = index_in_year + 1
        rows.append(
            {
                "year": year,
                # Năm mới hơn đứng trước trên landing.
                "sort_order": (newest_year - year) * 100 + index_in_year,
                "model_code": slugify_model(display_name),
                "display_name": display_name,
                "active": True,
            }
        )

    return rows


def upgrade() -> None:
    # ------------------------------------------------------------ iphone_models
    op.create_table(
        "iphone_models",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("model_code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_iphone_models"),
        sa.UniqueConstraint("model_code", name="uq_iphone_models_model_code"),
    )
    op.create_index(
        "ix_iphone_models_active_sort",
        "iphone_models",
        ["active", "sort_order"],
        unique=False,
    )

    # ------------------------------------------------------------ leads
    op.create_table(
        "leads",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gift_code", sa.String(length=32), nullable=False),
        sa.Column("full_name", sa.String(length=80), nullable=False),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("iphone_model", sa.String(length=120), nullable=False),
        sa.Column("iphone_year", sa.Integer(), nullable=False),
        sa.Column("case_color", sa.String(length=40), nullable=False),
        sa.Column("company_name", sa.String(length=120), nullable=True),
        sa.Column("bni_chapter", sa.String(length=80), nullable=True),
        sa.Column("referrer_name", sa.String(length=80), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("campaign", sa.String(length=64), nullable=True),
        sa.Column("utm_source", sa.String(length=64), nullable=True),
        sa.Column("utm_medium", sa.String(length=64), nullable=True),
        sa.Column("utm_campaign", sa.String(length=64), nullable=True),
        sa.Column("utm_content", sa.String(length=64), nullable=True),
        sa.Column("ref", sa.String(length=64), nullable=True),
        sa.Column("consent", sa.Boolean(), nullable=False),
        sa.Column(
            "gift_status",
            sa.String(length=16),
            server_default=sa.text("'NEW'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_by", sa.String(length=120), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_leads"),
        sa.UniqueConstraint("lead_id", name="uq_leads_lead_id"),
        sa.UniqueConstraint("gift_code", name="uq_leads_gift_code"),
        sa.CheckConstraint(
            "gift_status IN ('NEW','CONFIRMED','READY','REDEEMED','CANCELLED')",
            name="ck_leads_gift_status",
        ),
        sa.CheckConstraint("consent IS TRUE", name="ck_leads_consent_true"),
        sa.CheckConstraint("phone ~ '^0[35789][0-9]{8}$'", name="ck_leads_phone_canonical"),
    )
    op.create_index("ix_leads_phone", "leads", ["phone"], unique=False)
    op.create_index("ix_leads_created_at", "leads", ["created_at"], unique=False)
    op.create_index("ix_leads_gift_status", "leads", ["gift_status"], unique=False)
    op.create_index(
        "ix_leads_dup",
        "leads",
        ["phone", "iphone_model", "gift_status"],
        unique=False,
    )
    # Chốt chặn chống trùng ở tầng DATABASE.
    op.create_index(
        "uq_leads_active_duplicate",
        "leads",
        ["phone", "iphone_model"],
        unique=True,
        postgresql_where=sa.text("gift_status <> 'CANCELLED'"),
    )

    # ------------------------------------------------------------ audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("lead_pk", sa.BigInteger(), nullable=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("gift_code", sa.String(length=32), nullable=True),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        sa.UniqueConstraint("event_id", name="uq_audit_events_event_id"),
        sa.ForeignKeyConstraint(
            ["lead_pk"],
            ["leads.id"],
            name="fk_audit_events_lead_pk",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "event_type IN ('LEAD_CREATED','GIFT_CREATED','GIFT_STATUS_CHANGED','GIFT_REDEEMED')",
            name="ck_audit_events_event_type",
        ),
    )
    op.create_index(
        "ix_audit_events_gift_code_created",
        "audit_events",
        ["gift_code", "created_at"],
        unique=False,
    )
    op.create_index("ix_audit_events_lead_id", "audit_events", ["lead_id"], unique=False)
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"], unique=False)

    # ------------------------------------------------------------ seed danh mục
    op.bulk_insert(MODELS_TABLE, seed_rows())


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_lead_id", table_name="audit_events")
    op.drop_index("ix_audit_events_gift_code_created", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("uq_leads_active_duplicate", table_name="leads")
    op.drop_index("ix_leads_dup", table_name="leads")
    op.drop_index("ix_leads_gift_status", table_name="leads")
    op.drop_index("ix_leads_created_at", table_name="leads")
    op.drop_index("ix_leads_phone", table_name="leads")
    op.drop_table("leads")

    op.drop_index("ix_iphone_models_active_sort", table_name="iphone_models")
    op.drop_table("iphone_models")
