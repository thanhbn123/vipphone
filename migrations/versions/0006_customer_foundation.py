"""G13 — Nền móng khách hàng: `customers`, `customer_devices`, `customer_acquisition`
+ cột `leads.customer_id`.

Thiết kế đầy đủ: `docs/adr/0002-customer-identity.md`. Tóm tắt điều migration này PHẢI giữ:

1. KHÔNG xoá, KHÔNG sửa dòng `leads` nào — chỉ THÊM `customer_id`. Nhờ vậy
   `downgrade()` trả lại trạng thái cũ mà không mất dữ liệu.
2. IDEMPOTENT: chạy lại cho kết quả y hệt (`ON CONFLICT DO NOTHING`, chỉ điền khi NULL).
3. `leads.iphone_model` là TÊN HIỂN THỊ, không phải `model_code` ⇒ phải LEFT JOIN
   `iphone_models.display_name`. `display_name` KHÔNG UNIQUE nên join có thể ra 0
   hoặc >1 dòng — dùng `DISTINCT ON` + ghi NOTICE khi không khớp, KHÔNG dùng JOIN
   thường (dòng không khớp sẽ biến mất im lặng).
4. Nếu còn lead chưa gắn customer sau backfill ⇒ NỔ, không đi tiếp.

Revision ID: 0006_customer_foundation
Revises: 0005_single_address
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0006_customer_foundation"
down_revision: str | None = "0005_single_address"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("customer_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("phone_normalized", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("company_name", sa.String(length=120), nullable=True),
        sa.Column("bni_chapter", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("marketing_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consent_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("customer_id", name="uq_customers_customer_id"),
        # Danh tính = SĐT chuẩn hoá. UNIQUE ở TẦNG DB vì ràng buộc chỉ ở tầng ứng
        # dụng thì hai request đồng thời vẫn lọt (bài học từ chống trùng gift).
        sa.UniqueConstraint("phone_normalized", name="uq_customers_phone_normalized"),
        sa.CheckConstraint("status IN ('ACTIVE','BLOCKED','MERGED')", name="ck_customers_status"),
    )

    op.create_table(
        "customer_devices",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("brand", sa.String(length=40), nullable=False, server_default="Apple"),
        sa.Column("model_code", sa.String(length=64), nullable=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("color", sa.String(length=40), nullable=True),
        sa.Column("storage", sa.String(length=20), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            ondelete="CASCADE",
            name="fk_customer_devices_customer",
        ),
        sa.UniqueConstraint("customer_id", "model_code", name="uq_customer_devices_customer_model"),
    )
    # ĐÚNG MỘT máy chính mỗi khách — partial unique index biến "vô tình có hai máy
    # chính" thành lỗi bắt được, thay vì sai lặng lẽ.
    op.create_index(
        "uq_customer_devices_one_primary",
        "customer_devices",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )

    op.create_table(
        "customer_acquisition",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("referrer_name", sa.String(length=120), nullable=True),
        sa.Column("ref", sa.String(length=64), nullable=True),
        sa.Column("utm_source", sa.String(length=64), nullable=True),
        sa.Column("utm_medium", sa.String(length=64), nullable=True),
        sa.Column("utm_campaign", sa.String(length=64), nullable=True),
        sa.Column("utm_content", sa.String(length=64), nullable=True),
        sa.Column("first_gift_code", sa.String(length=32), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            ondelete="CASCADE",
            name="fk_customer_acquisition_customer",
        ),
        # FIRST-TOUCH: một dòng mỗi khách, ghi lần đầu, lead sau không ghi đè.
        sa.UniqueConstraint("customer_id", name="uq_customer_acquisition_customer"),
    )

    op.add_column("leads", sa.Column("customer_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_leads_customer", "leads", "customers", ["customer_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_leads_customer_id", "leads", ["customer_id"])

    # ---------- BACKFILL (bảo toàn, idempotent) ----------
    op.execute(
        sa.text("""
        INSERT INTO customers (customer_id, full_name, phone_normalized, email,
                               company_name, bni_chapter, status, marketing_consent,
                               consent_updated_at, created_at, updated_at)
        SELECT gen_random_uuid(), f.full_name, f.phone, f.email, f.company_name,
               f.bni_chapter, 'ACTIVE', COALESCE(c.any_consent, false),
               CASE WHEN COALESCE(c.any_consent, false) THEN now() ELSE NULL END,
               f.created_at, now()
        FROM (SELECT DISTINCT ON (phone) * FROM leads ORDER BY phone, created_at, id) f
        LEFT JOIN (SELECT phone, bool_or(consent) AS any_consent FROM leads GROUP BY phone) c
               ON c.phone = f.phone
        ON CONFLICT (phone_normalized) DO NOTHING
    """)
    )

    op.execute(
        sa.text("""
        UPDATE leads l SET customer_id = c.id
        FROM customers c
        WHERE c.phone_normalized = l.phone AND l.customer_id IS NULL
    """)
    )

    # Máy CHÍNH = máy của lead MỚI NHẤT. LEFT JOIN để dòng không khớp vẫn được ghi
    # (model_code NULL) thay vì biến mất.
    op.execute(
        sa.text("""
        INSERT INTO customer_devices (customer_id, brand, model_code, display_name,
                                      year, is_primary, created_at, updated_at)
        SELECT DISTINCT ON (l.customer_id)
               l.customer_id, 'Apple', m.model_code, l.iphone_model, l.iphone_year,
               true, l.created_at, now()
        FROM leads l
        LEFT JOIN (SELECT DISTINCT ON (display_name) display_name, model_code
                   FROM iphone_models ORDER BY display_name, sort_order, id) m
               ON m.display_name = l.iphone_model
        WHERE l.customer_id IS NOT NULL
        ORDER BY l.customer_id, l.created_at DESC, l.id DESC
        ON CONFLICT (customer_id, model_code) DO NOTHING
    """)
    )

    op.execute(
        sa.text("""
        INSERT INTO customer_acquisition (customer_id, source, referrer_name, ref,
                                          utm_source, utm_medium, utm_campaign,
                                          utm_content, first_gift_code, first_seen_at)
        SELECT DISTINCT ON (l.customer_id)
               l.customer_id, l.source, l.referrer_name, l.ref, l.utm_source,
               l.utm_medium, l.utm_campaign, l.utm_content, l.gift_code, l.created_at
        FROM leads l WHERE l.customer_id IS NOT NULL
        ORDER BY l.customer_id, l.created_at, l.id
        ON CONFLICT (customer_id) DO NOTHING
    """)
    )

    # Ghi ra số dòng KHÔNG khớp model — đây là chỗ dễ hỏng im lặng nhất.
    op.execute(
        sa.text("""
        DO $$
        DECLARE n int;
        BEGIN
          SELECT count(*) INTO n FROM leads l
          LEFT JOIN iphone_models m ON m.display_name = l.iphone_model
          WHERE m.id IS NULL;
          IF n > 0 THEN
            RAISE NOTICE 'G13: % lead co iphone_model KHONG khop iphone_models.display_name -> model_code = NULL', n;
          END IF;
        END $$;
    """)
    )

    # Chốt an toàn: còn lead chưa gắn customer thì NỔ, không đi tiếp.
    op.execute(
        sa.text("""
        DO $$
        DECLARE n int;
        BEGIN
          SELECT count(*) INTO n FROM leads WHERE customer_id IS NULL;
          IF n > 0 THEN
            RAISE EXCEPTION 'Backfill G13 that bai: con % lead chua gan customer', n;
          END IF;
        END $$;
    """)
    )


def downgrade() -> None:
    op.drop_index("ix_leads_customer_id", table_name="leads")
    op.drop_constraint("fk_leads_customer", "leads", type_="foreignkey")
    op.drop_column("leads", "customer_id")
    op.drop_table("customer_acquisition")
    op.drop_index("uq_customer_devices_one_primary", table_name="customer_devices")
    op.drop_table("customer_devices")
    op.drop_table("customers")
