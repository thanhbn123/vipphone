"""G14 — Danh mục sản phẩm: `categories`, `products`, `product_variants`,
`device_compatibility` + seed 10 category.

Thiết kế đầy đủ: `docs/catalog.md`. Tóm tắt điều migration này PHẢI giữ:

1. ADDITIVE — KHÔNG sửa một dòng nào của `0001`..`0006`. Chỉ `CREATE TABLE` + seed.
   Nhờ vậy `downgrade()` trả lại trạng thái cũ mà lead/khách/gift còn nguyên.
2. TIỀN là `Numeric(12,2)` — TUYỆT ĐỐI KHÔNG `float`. `float` là số nhị phân nên
   sinh sai số (`0.1 + 0.2 != 0.3`); giá đã ghi vào đơn là thứ không migration nào
   vá được về sau.
3. UNIQUE ở TẦNG DB cho `code`/`slug`/`product_id`/`sku`: ràng buộc chỉ ở tầng ứng
   dụng thì hai request đồng thời cùng `SELECT` thấy "chưa có" rồi cùng `INSERT`
   vẫn lọt — đúng bài học của chính sách chống trùng gift và `customers.phone_normalized`.
4. CHECK `compare_at_price >= sale_price`: giá gạch nhỏ hơn giá bán là NÓI DỐI
   khách hàng, chặn ở DB để không phụ thuộc vào việc mọi đường ghi đều nhớ kiểm.
5. SEED đúng 10 category, deterministic + idempotent (`ON CONFLICT (code) DO NOTHING`).
   KHÔNG seed sản phẩm nào: category là *từ vựng*, sản phẩm là *dữ liệu kinh doanh*
   (chỉ có thật khi người thật nhập giá thật). Seed sản phẩm giả là bịa dữ liệu.
6. `stock_tracking` chỉ là CỜ, không phải tồn kho — G14 chưa có inventory engine.

Revision ID: 0007_product_catalog
Revises: 0006_customer_foundation
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0007_product_catalog"
down_revision: str | None = "0006_customer_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: 10 category — TỪ VỰNG phân loại, không phải dữ liệu bán hàng.
#: Thứ tự trong danh sách này CHÍNH LÀ `sort_order` (0..9) ⇒ deterministic.
#:
#: ⚠️  G14 KHÔNG có đường GHI nào cho `categories` (không route POST/PATCH/DELETE).
#: Đổi `name`, đổi `sort_order`, hay đặt `active = false` HIỆN CHỈ LÀM ĐƯỢC BẰNG SQL
#: trực tiếp trên DB:
#:     UPDATE categories SET active = false WHERE code = 'STAND';
#: Đây là chủ ý (nhẹ hơn mở thêm route admin cho một bảng từ vựng), không phải sót.
#: Xem `docs/catalog.md` §2.1 và §8. Route admin cho category là việc mở.
SEED_CATEGORIES: list[tuple[str, str]] = [
    ("CASE", "Ốp lưng"),
    ("SCREEN_PROTECTOR", "Dán màn hình"),
    ("CABLE", "Cáp sạc"),
    ("CHARGER", "Củ sạc"),
    ("POWER_BANK", "Pin dự phòng"),
    ("EARPHONE", "Tai nghe"),
    ("MAGSAFE", "Phụ kiện MagSafe"),
    ("CAR_ACCESSORY", "Phụ kiện ô tô"),
    ("STAND", "Giá đỡ"),
    ("OTHER", "Khác"),
]

#: Loại tương thích cho phép — TRÙNG KHỚP với CHECK constraint bên dưới.
COMPATIBILITY_TYPES = ("FULL", "PARTIAL", "CASE_FIT")


def upgrade() -> None:
    # ---------------------------------------------------------- categories
    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # `code` là slug ổn định, xuất hiện trong URL lọc và trong câu lệnh kiểm
        # tra trên staging ⇒ phải UNIQUE thật ở DB, không chỉ kiểm ở ứng dụng.
        sa.UniqueConstraint("code", name="uq_categories_code"),
        sa.CheckConstraint("code = upper(code)", name="ck_categories_code_upper"),
    )

    # ------------------------------------------------------------ products
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("product_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("brand", sa.String(length=80), nullable=True),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # UUID là định danh CÔNG KHAI; `id` bigint là khoá nội bộ, không lộ ra ngoài
        # (cùng nếp `leads.lead_id` + `leads.id`).
        sa.UniqueConstraint("product_id", name="uq_products_product_id"),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
        # RESTRICT: xoá category còn sản phẩm là phá dữ liệu. Muốn ẩn thì đặt
        # `active = false`, KHÔNG xoá.
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            ondelete="RESTRICT",
            name="fk_products_category",
        ),
    )
    op.create_index("ix_products_category_active", "products", ["category_id", "active"])
    op.create_index("ix_products_active_name", "products", ["active", "name"])

    # ---------------------------------------------------- product_variants
    op.create_table(
        "product_variants",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("variant_name", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=40), nullable=True),
        # TIỀN: Numeric(12,2) — không float. Xem docstring đầu file.
        sa.Column("cost_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("sale_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("compare_at_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="VND"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        # CỜ thôi — G14 CHƯA có inventory engine, cột này KHÔNG sinh ra số lượng.
        sa.Column("stock_tracking", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("sku", name="uq_product_variants_sku"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="CASCADE",
            name="fk_product_variants_product",
        ),
        sa.CheckConstraint("sale_price >= 0", name="ck_product_variants_sale_price_non_negative"),
        sa.CheckConstraint(
            "cost_price IS NULL OR cost_price >= 0",
            name="ck_product_variants_cost_price_non_negative",
        ),
        # Giá gạch nhỏ hơn giá bán = nói dối khách. Chặn ở DB.
        sa.CheckConstraint(
            "compare_at_price IS NULL OR compare_at_price >= sale_price",
            name="ck_product_variants_compare_at_not_below_sale",
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_product_variants_currency_format"),
    )
    op.create_index(
        "ix_product_variants_product_active", "product_variants", ["product_id", "active"]
    )

    # ------------------------------------------------- device_compatibility
    op.create_table(
        "device_compatibility",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column("device_brand", sa.String(length=40), nullable=False, server_default="Apple"),
        # Khoá join là MÃ (`iphone-16-pro-max`), KHÔNG phải tên hiển thị
        # (`iPhone 16 Pro Max`): `iphone_models.display_name` KHÔNG UNIQUE nên join
        # qua nó có thể ra 0 hoặc >1 dòng (ADR-0002 §2.4). Dùng mã ⇒ so chuỗi chính
        # xác, không thể nhân bản dòng.
        sa.Column("device_model_code", sa.String(length=64), nullable=False),
        sa.Column("compatibility_type", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # Cùng một SKU không khai hai lần cho cùng một máy — nếu không, khai trùng
        # tích luỹ dần mà không ai phát hiện.
        sa.UniqueConstraint(
            "sku_id",
            "device_brand",
            "device_model_code",
            name="uq_device_compatibility_sku_device",
        ),
        sa.ForeignKeyConstraint(
            ["sku_id"],
            ["product_variants.id"],
            ondelete="CASCADE",
            name="fk_device_compatibility_sku",
        ),
        sa.CheckConstraint(
            "compatibility_type IN ('FULL','PARTIAL','CASE_FIT')",
            name="ck_device_compatibility_type",
        ),
    )
    op.create_index(
        "ix_device_compatibility_lookup",
        "device_compatibility",
        ["device_brand", "device_model_code"],
    )

    # ------------------------------------------------------------ seed
    # Deterministic + IDEMPOTENT. `DO NOTHING` (không phải `DO UPDATE`) là cố ý:
    # chạy lại migration sau khi admin đã sửa tên category thì KHÔNG ghi đè tên
    # admin đặt — seed chỉ tạo cái còn thiếu.
    #
    # KHÔNG seed sản phẩm nào. Xem docstring đầu file, mục 5.
    rows = ", ".join(
        f"('{code}', '{name}', {index}, true)" for index, (code, name) in enumerate(SEED_CATEGORIES)
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO categories (code, name, sort_order, active)
            VALUES {rows}
            ON CONFLICT (code) DO NOTHING
            """
        )
    )

    # Chốt an toàn: đủ 10 category phải có mặt sau seed. Thiếu ⇒ NỔ, không đi tiếp.
    # Không đếm TỔNG số dòng (admin có thể đã thêm category khác — đó là hợp lệ).
    codes = ", ".join(f"'{code}'" for code, _ in SEED_CATEGORIES)
    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE n int;
            BEGIN
              SELECT count(*) INTO n FROM categories WHERE code IN ({codes});
              IF n <> {len(SEED_CATEGORIES)} THEN
                RAISE EXCEPTION 'Seed G14 that bai: chi co % / {len(SEED_CATEGORIES)} category',
                                n;
              END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    # Thứ tự NGƯỢC chiều phụ thuộc: con trước, cha sau.
    op.drop_index("ix_device_compatibility_lookup", table_name="device_compatibility")
    op.drop_table("device_compatibility")
    op.drop_index("ix_product_variants_product_active", table_name="product_variants")
    op.drop_table("product_variants")
    op.drop_index("ix_products_active_name", table_name="products")
    op.drop_index("ix_products_category_active", table_name="products")
    op.drop_table("products")
    op.drop_table("categories")
