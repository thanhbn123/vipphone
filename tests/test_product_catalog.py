"""G14 — Danh mục sản phẩm. Thiết kế: `docs/catalog.md`.

Điều quan trọng nhất bộ test này bảo vệ:

1. **Ranh giới công khai/quản trị**: hàng đã tắt KHÔNG được lộ ra ngoài, và
   `cost_price` (giá nhập) KHÔNG BAO GIỜ có trong JSON công khai.
2. **Tiền là `Decimal`**, không phải `float` — sai số nhị phân trên giá là thứ
   không migration nào vá được về sau.
3. **Ràng buộc UNIQUE sống ở TẦNG DB** (`slug`, `sku`), không chỉ ở ứng dụng.
4. **Lọc theo thiết bị không nhân bản dòng** — nhiều SKU cùng khớp một máy vẫn
   chỉ trả MỘT sản phẩm.

Ba đối chứng âm thật (phá mã nguồn rồi đo) ghi ở `docs/MASTER_STATUS.md` §36.
Các hàm `test_NEGATIVE_control_*` dưới đây là lớp thứ hai: chúng chứng minh
phép đo **phân biệt được** đúng và sai, chứ không phải luôn xanh.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import Category, DeviceCompatibility, Product, ProductVariant

# V6: bộ này chạy trên PostgreSQL THẬT (fixture `db`/`client` của `conftest.py`
# dựng schema bằng migration rồi TRUNCATE trước mỗi test). Thiếu dấu này thì bước
# CI tên "Integration tests (PostgreSQL)" — `pytest -m integration` — KHÔNG chạy
# một bài nào của tệp này, dù chúng đều là test tích hợp. Đo được: trước khi thêm,
# `-m integration` chọn 0/36 bài của tệp này.
pytestmark = pytest.mark.integration

PRODUCT_PAYLOAD = {
    "name": "Ốp lưu niệm VIP",
    "slug": "op-luu-niem-vip",
    "category_code": "CASE",
    "brand": "VIPPHONE",
    "description": "Ốp demo cho test — KHÔNG phải dữ liệu bán thật.",
}


def _create_product(client, staff_headers, **overrides) -> dict:
    payload = {**PRODUCT_PAYLOAD, **overrides}
    response = client.post("/api/admin/products", json=payload, headers=staff_headers)
    assert response.status_code == 201, response.text
    return response.json()


def _create_variant(client, staff_headers, product_id: str, **overrides) -> dict:
    payload = {
        "sku": "OP-VIP-01",
        "variant_name": "Đen",
        "sale_price": "250000.00",
        "compare_at_price": "300000.00",
        "cost_price": "120000.00",
        "currency": "VND",
        **overrides,
    }
    response = client.post(
        f"/api/admin/products/{product_id}/variants", json=payload, headers=staff_headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_compatibility(client, staff_headers, sku: str, model_code: str, kind: str = "FULL"):
    response = client.post(
        f"/api/admin/variants/{sku}/compatibility",
        json={"device_model_code": model_code, "compatibility_type": kind},
        headers=staff_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# ==========================================================================
# Migration + schema
# ==========================================================================
def test_migration_creates_catalog_tables_and_seeds_ten_categories(db):
    """Migration chạy được ⇒ 4 bảng có mặt và ĐÚNG 10 category đã seed."""
    expected = {
        "CASE",
        "SCREEN_PROTECTOR",
        "CABLE",
        "CHARGER",
        "POWER_BANK",
        "EARPHONE",
        "MAGSAFE",
        "CAR_ACCESSORY",
        "STAND",
        "OTHER",
    }
    codes = {c.code for c in db.execute(select(Category)).scalars().all()}
    assert codes == expected, f"seed category lệch: {codes ^ expected}"

    # Bảng thật sự tồn tại trong DB (không chỉ trong mã).
    for table in ("products", "product_variants", "device_compatibility"):
        assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0, (
            f"{table} phải RỖNG sau migration — KHÔNG seed sản phẩm giả"
        )


def test_money_columns_are_numeric_not_float(db):
    """Kiểu cột tiền là `numeric(12,2)`. `float`/`double precision` = test ĐỎ."""
    rows = db.execute(
        text(
            """
            SELECT column_name, data_type, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_name = 'product_variants'
              AND column_name IN ('cost_price', 'sale_price', 'compare_at_price')
            """
        )
    ).all()
    assert len(rows) == 3, rows
    for column_name, data_type, precision, scale in rows:
        assert data_type == "numeric", f"{column_name} là {data_type} — TIỀN PHẢI là numeric"
        assert (precision, scale) == (12, 2), f"{column_name} là numeric({precision},{scale})"


# ==========================================================================
# Ranh giới công khai / quản trị
# ==========================================================================
def test_public_list_hides_inactive_product(client, staff_headers):
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"])

    assert client.get("/api/products").json()["total"] == 1

    off = client.patch(
        f"/api/admin/products/{created['product_id']}",
        json={"active": False},
        headers=staff_headers,
    )
    assert off.status_code == 200, off.text
    assert off.json()["active"] is False

    public = client.get("/api/products").json()
    assert public["total"] == 0, "sản phẩm đã tắt vẫn hiện ở danh sách công khai!"
    assert public["items"] == []


def test_public_detail_returns_404_for_inactive_product(client, staff_headers):
    created = _create_product(client, staff_headers)
    client.patch(
        f"/api/admin/products/{created['product_id']}",
        json={"active": False},
        headers=staff_headers,
    )
    response = client.get(f"/api/products/{PRODUCT_PAYLOAD['slug']}")
    assert response.status_code == 404, "sản phẩm đã tắt vẫn xem được công khai!"


def test_public_hides_inactive_sku(client, staff_headers):
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"], sku="OP-VIP-ON")
    _create_variant(client, staff_headers, created["product_id"], sku="OP-VIP-OFF")

    off = client.patch(
        "/api/admin/variants/OP-VIP-OFF", json={"active": False}, headers=staff_headers
    )
    assert off.status_code == 200, off.text

    body = client.get(f"/api/products/{PRODUCT_PAYLOAD['slug']}").json()
    assert [v["sku"] for v in body["variants"]] == ["OP-VIP-ON"], "SKU đã tắt vẫn lộ ra công khai!"


def test_admin_sees_inactive_product_and_sku(client, staff_headers):
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"], sku="OP-VIP-OFF")
    client.patch(
        f"/api/admin/products/{created['product_id']}",
        json={"active": False},
        headers=staff_headers,
    )
    client.patch("/api/admin/variants/OP-VIP-OFF", json={"active": False}, headers=staff_headers)

    listing = client.get("/api/admin/products", headers=staff_headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1, "quản trị PHẢI thấy sản phẩm đã tắt để bật lại"

    detail = client.get(
        f"/api/admin/products/{created['product_id']}", headers=staff_headers
    ).json()
    assert detail["active"] is False
    assert [v["sku"] for v in detail["variants"]] == ["OP-VIP-OFF"]
    assert detail["variants"][0]["active"] is False


def test_public_json_never_exposes_cost_price(client, staff_headers):
    """`cost_price` là giá NHẬP. Lộ ra là lộ biên lợi nhuận."""
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"])
    _add_compatibility(client, staff_headers, "OP-VIP-01", "iphone-16-pro-max")

    raw_list = client.get("/api/products").text
    raw_detail = client.get(f"/api/products/{PRODUCT_PAYLOAD['slug']}").text
    for raw in (raw_list, raw_detail):
        assert "cost_price" not in raw, "giá nhập bị trả ra đường công khai!"
        assert "120000" not in raw, "giá nhập bị trả ra đường công khai!"

    admin_raw = client.get("/api/admin/products", headers=staff_headers).text
    assert "cost_price" in admin_raw, "quản trị PHẢI thấy giá nhập"


def test_selling_below_cost_price_is_allowed(client, staff_headers):
    """V11 — BÁN DƯỚI GIÁ NHẬP là ca HỢP LỆ (xả hàng), không phải lỗi dữ liệu.

    §4 của `docs/catalog.md` liệt kê 5 luật giá nhưng TRƯỚC BẢN VÁ không nhắc luật
    này, nên người đọc tài liệu không biết hệ thống cố ý cho phép hay bỏ sót. Đo
    được trên bản cũ: `sale_price 100.00` + `cost_price 999.00` ⇒ **201**. Hành vi
    đó ĐÚNG và được GIỮ NGUYÊN — bài này chốt lại để lần sau ai thêm ràng buộc
    `sale_price >= cost_price` thì biết ngay mình vừa đổi luật nghiệp vụ.

    Vì sao KHÔNG chặn: xả hàng tồn, bán lỗ có chủ đích, và bán dưới giá nhập để
    đẩy dòng tiền là quyết định của Owner — một CHECK ở DB sẽ chặn luôn quyết định
    đó mà không nói được lý do cho ai. Ghi vào tài liệu, không chặn ở DB.
    """
    created = _create_product(client, staff_headers)
    response = client.post(
        f"/api/admin/products/{created['product_id']}/variants",
        json={
            "sku": "OP-BAN-LO-01",
            "variant_name": "Xả hàng tồn",
            "sale_price": "100.00",
            "cost_price": "999.00",
            "currency": "VND",
        },
        headers=staff_headers,
    )
    assert response.status_code == 201, (
        "bán dưới giá nhập phải được PHÉP (xả hàng) — nếu ai đó thêm ràng buộc "
        f"sale_price >= cost_price thì đổi luật và phải sửa docs/catalog.md §4: {response.text}"
    )
    # Endpoint trả CẢ sản phẩm (`AdminProductOut`), không trả riêng SKU.
    variant = response.json()["variants"][0]
    assert Decimal(variant["sale_price"]) == Decimal("100.00")
    assert Decimal(variant["cost_price"]) == Decimal("999.00")
    assert Decimal(variant["sale_price"]) < Decimal(variant["cost_price"])

    # Bán dưới giá nhập KHÔNG được kéo theo việc lộ giá nhập ra công khai.
    # So theo GIÁ TRỊ, không theo chuỗi con: "999" từng khớp ngẫu nhiên vào UUID /
    # micro-giây của timestamp ⇒ test đỏ thất thường (#88, lộ ra khi deploy chạy test).
    public = client.get(f"/api/products/{PRODUCT_PAYLOAD['slug']}")
    assert "cost_price" not in public.text

    def _scalars(node):
        if isinstance(node, dict):
            for value in node.values():
                yield from _scalars(value)
        elif isinstance(node, list):
            for value in node:
                yield from _scalars(value)
        else:
            yield node

    def _is_cost(value) -> bool:
        try:
            return Decimal(str(value)) == Decimal("999.00")
        except (ArithmeticError, ValueError):
            return False

    leaked = [v for v in _scalars(public.json()) if not isinstance(v, bool) and _is_cost(v)]
    assert not leaked, f"giá nhập lộ ra trang công khai: {leaked}"


def test_availability_is_never_a_quantity(client, staff_headers):
    """Nhãn tồn kho chỉ có hai giá trị. Không có con số nào — chưa có sổ kho."""
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"])
    body = client.get(f"/api/products/{PRODUCT_PAYLOAD['slug']}").json()
    assert body["availability"] == "IN_STOCK"
    assert not any(ch.isdigit() for ch in body["availability"]), "nhãn tồn kho chứa số lượng!"

    # Không có trường số lượng nào trong JSON công khai.
    for forbidden in ("quantity", "stock", "inventory", "stock_quantity", "stock_tracking"):
        assert forbidden not in client.get(f"/api/products/{PRODUCT_PAYLOAD['slug']}").text, (
            f"JSON công khai có trường tồn kho {forbidden!r} — chưa có inventory engine"
        )


# ==========================================================================
# Ràng buộc UNIQUE ở TẦNG DB
# ==========================================================================
def test_slug_is_unique(client, staff_headers):
    _create_product(client, staff_headers)
    duplicate = client.post(
        "/api/admin/products", json={**PRODUCT_PAYLOAD, "name": "Trùng slug"}, headers=staff_headers
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "DUPLICATE_VALUE"


def test_sku_is_unique(client, staff_headers):
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"], sku="OP-VIP-DUP")
    duplicate = client.post(
        f"/api/admin/products/{created['product_id']}/variants",
        json={
            "sku": "OP-VIP-DUP",
            "variant_name": "Bản sao",
            "sale_price": "100000.00",
        },
        headers=staff_headers,
    )
    assert duplicate.status_code == 409, duplicate.text


def test_unique_constraints_exist_at_database_level(db, client, staff_headers):
    """UNIQUE ở DB thật — không chỉ là lời hứa ở tầng ứng dụng.

    Vì sao phải đo ở DB: hai request đồng thời cùng `SELECT` thấy "chưa có" rồi
    cùng `INSERT` thì tầng ứng dụng KHÔNG chặn được. Chỉ ràng buộc DB chặn.
    """
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"])

    # --- slug trùng: chèn thẳng, bỏ qua mọi kiểm tra của ứng dụng
    other_category = db.execute(select(Category).where(Category.code == "OTHER")).scalar_one()
    db.add(
        Product(
            product_id=uuid.uuid4(),
            name="Bản sao",
            slug=PRODUCT_PAYLOAD["slug"],
            category_id=other_category.id,
            active=True,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    # --- sku trùng
    product = db.execute(
        select(Product).where(Product.slug == PRODUCT_PAYLOAD["slug"])
    ).scalar_one()
    db.add(
        ProductVariant(
            sku="OP-VIP-01",
            product_id=product.id,
            variant_name="Bản sao",
            sale_price=Decimal("100000.00"),
            currency="VND",
            active=True,
            stock_tracking=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# ==========================================================================
# Tiền
# ==========================================================================
def test_prices_round_trip_exactly_as_decimal(client, staff_headers):
    """Giá lưu và đọc lại ĐÚNG TỪNG ĐỒNG — không có sai số kiểu float."""
    created = _create_product(client, staff_headers)
    _create_variant(
        client,
        staff_headers,
        created["product_id"],
        sku="OP-VIP-PRICE",
        sale_price="250000.10",
        compare_at_price="250000.20",
        cost_price="123456.78",
    )
    body = client.get(f"/api/products/{PRODUCT_PAYLOAD['slug']}").json()
    variant = body["variants"][0]
    assert Decimal(variant["sale_price"]) == Decimal("250000.10")
    assert Decimal(variant["compare_at_price"]) == Decimal("250000.20")

    admin = client.get(f"/api/admin/products/{created['product_id']}", headers=staff_headers).json()
    assert Decimal(admin["variants"][0]["cost_price"]) == Decimal("123456.78")


def test_compare_at_price_below_sale_price_is_rejected(client, staff_headers):
    """Giá gạch nhỏ hơn giá bán = nói dối khách. Chặn ở lược đồ (422) VÀ ở DB."""
    created = _create_product(client, staff_headers)
    response = client.post(
        f"/api/admin/products/{created['product_id']}/variants",
        json={
            "sku": "OP-VIP-LIE",
            "variant_name": "Giá ảo",
            "sale_price": "200000.00",
            "compare_at_price": "100000.00",
        },
        headers=staff_headers,
    )
    assert response.status_code == 422, response.text

    # Không có SKU nào được ghi (không phải chỉ báo lỗi rồi vẫn lưu).
    after = client.get(f"/api/admin/products/{created['product_id']}", headers=staff_headers).json()
    assert after["variants"] == []


def test_patch_variant_cannot_make_compare_at_below_sale(client, staff_headers):
    """Sửa CHỈ `sale_price` cũng phải đối chiếu `compare_at_price` đang có trong DB."""
    created = _create_product(client, staff_headers)
    _create_variant(
        client,
        staff_headers,
        created["product_id"],
        sku="OP-VIP-PATCH",
        sale_price="200000.00",
        compare_at_price="300000.00",
    )
    bumped = client.patch(
        "/api/admin/variants/OP-VIP-PATCH",
        json={"sale_price": "400000.00"},
        headers=staff_headers,
    )
    assert bumped.status_code == 422, bumped.text

    # Đối chứng dương: hạ giá trong khoảng hợp lệ thì được.
    ok = client.patch(
        "/api/admin/variants/OP-VIP-PATCH",
        json={"sale_price": "250000.00"},
        headers=staff_headers,
    )
    assert ok.status_code == 200, ok.text


def test_negative_prices_are_rejected(client, staff_headers):
    created = _create_product(client, staff_headers)
    for field in ("sale_price", "cost_price", "compare_at_price"):
        payload = {
            "sku": f"OP-NEG-{field}",
            "variant_name": "Âm",
            "sale_price": "100000.00",
        }
        payload[field] = "-1.00"
        response = client.post(
            f"/api/admin/products/{created['product_id']}/variants",
            json=payload,
            headers=staff_headers,
        )
        assert response.status_code == 422, f"{field} âm vẫn lọt: {response.text}"


# ==========================================================================
# Tương thích thiết bị
# ==========================================================================
def test_compatibility_filter_by_device(client, staff_headers):
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"])
    _add_compatibility(client, staff_headers, "OP-VIP-01", "iphone-16-pro-max")

    matched = client.get("/api/products", params={"device_model": "iphone-16-pro-max"}).json()
    assert matched["total"] == 1

    missed = client.get("/api/products", params={"device_model": "iphone-14"}).json()
    assert missed["total"] == 0, "lọc theo máy không khớp mà vẫn ra sản phẩm!"


def test_compatibility_filter_does_not_duplicate_rows(client, staff_headers):
    """Ba SKU cùng tương thích một máy ⇒ vẫn ĐÚNG MỘT dòng.

    Nếu truy vấn dùng `JOIN` thay vì `EXISTS`, test này đỏ với `total == 3`.
    """
    created = _create_product(client, staff_headers)
    for index in range(3):
        sku = f"OP-VIP-M{index}"
        _create_variant(client, staff_headers, created["product_id"], sku=sku)
        _add_compatibility(client, staff_headers, sku, "iphone-16-pro-max")

    body = client.get("/api/products", params={"device_model": "iphone-16-pro-max"}).json()
    assert body["total"] == 1, f"sản phẩm bị nhân bản {body['total']} lần!"
    assert len(body["items"]) == 1


def test_inactive_sku_does_not_match_device_filter(client, staff_headers):
    """SKU đã tắt thì không được kéo sản phẩm vào kết quả lọc theo máy."""
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"], sku="OP-VIP-OFFDEV")
    _add_compatibility(client, staff_headers, "OP-VIP-OFFDEV", "iphone-15")
    client.patch("/api/admin/variants/OP-VIP-OFFDEV", json={"active": False}, headers=staff_headers)

    body = client.get("/api/products", params={"device_model": "iphone-15"}).json()
    assert body["total"] == 0


def test_compatibility_duplicate_declaration_rejected(client, staff_headers):
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"])
    _add_compatibility(client, staff_headers, "OP-VIP-01", "iphone-16-pro-max")
    again = client.post(
        "/api/admin/variants/OP-VIP-01/compatibility",
        json={"device_model_code": "iphone-16-pro-max", "compatibility_type": "FULL"},
        headers=staff_headers,
    )
    assert again.status_code == 409, again.text


def test_compatibility_can_be_declared_and_removed(client, staff_headers):
    created = _create_product(client, staff_headers)
    body = _create_variant(client, staff_headers, created["product_id"])
    assert body["variants"][0]["compatibility"] == []

    declared = _add_compatibility(client, staff_headers, "OP-VIP-01", "iphone-17-pro", "PARTIAL")
    variant = declared["variants"][0]
    assert variant["compatibility"][0]["device_model_code"] == "iphone-17-pro"
    assert variant["compatibility"][0]["compatibility_type"] == "PARTIAL"

    listing = client.get(
        f"/api/admin/products/{created['product_id']}", headers=staff_headers
    ).json()
    compat_id = listing["variants"][0]["compatibility"][0]["id"]

    removed = client.delete(
        f"/api/admin/variants/OP-VIP-01/compatibility/{compat_id}", headers=staff_headers
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["variants"][0]["compatibility"] == []


# ==========================================================================
# Lọc + tìm kiếm + phân trang
# ==========================================================================
def test_keyword_search_by_name_and_sku(client, staff_headers):
    first = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, first["product_id"], sku="OP-ALPHA-01")

    second = _create_product(
        client,
        staff_headers,
        name="Cáp sạc nhanh 20W",
        slug="cap-sac-nhanh-20w",
        category_code="CABLE",
    )
    _create_variant(client, staff_headers, second["product_id"], sku="CABLE-BETA-02")

    by_name = client.get("/api/products", params={"q": "Cáp sạc"}).json()
    assert by_name["total"] == 1
    assert by_name["items"][0]["slug"] == "cap-sac-nhanh-20w"

    by_sku = client.get("/api/products", params={"q": "ALPHA"}).json()
    assert by_sku["total"] == 1
    assert by_sku["items"][0]["slug"] == PRODUCT_PAYLOAD["slug"]

    nothing = client.get("/api/products", params={"q": "khong-co-gi-khop"}).json()
    assert nothing["total"] == 0


def test_keyword_wildcards_are_escaped(client, staff_headers):
    """Gõ `%` KHÔNG được biến ô tìm kiếm thành "trả về tất cả"."""
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"])

    for wildcard in ("%", "_", "%%", "\\"):
        body = client.get("/api/products", params={"q": wildcard}).json()
        assert body["total"] == 0, f"ký tự {wildcard!r} khớp tất cả — chưa escape LIKE!"


def test_keyword_search_does_not_match_deactivated_sku(client, staff_headers):
    """V4 — SKU ĐÃ TẮT không được kéo sản phẩm cha lên tìm kiếm CÔNG KHAI.

    LỖI ĐÃ ĐO ĐƯỢC: nhánh `q` trong `product_query` chỉ so `ProductVariant.sku`
    mà THIẾU `ProductVariant.active.is_(True)`, trong khi nhánh `device_model`
    (`_compatible_exists`) và `active_only` đều đã lọc. Đo trên bản cũ: tạo SKU
    đã tắt `SKU-AN-DA-TAT` ⇒ `GET /api/products?q=SKU-AN-DA-TAT` trả **total: 1**.

    Vì sao vẫn là lỗi dù danh sách SKU trả về rỗng: khách gõ đúng mã hàng đã
    ngừng bán thì thấy SẢN PHẨM hiện ra ở `/shop`. Đó là xác nhận sự tồn tại của
    một món không còn bán — và `total` dùng cho phân trang cũng sai.
    """
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"], sku="SKU-AN-DA-TAT")
    _create_variant(client, staff_headers, created["product_id"], sku="SKU-CON-BAN")

    # Trước khi tắt: tìm theo SKU đang bán phải thấy.
    assert client.get("/api/products", params={"q": "SKU-CON-BAN"}).json()["total"] == 1

    response = client.patch(
        "/api/admin/variants/SKU-AN-DA-TAT", json={"active": False}, headers=staff_headers
    )
    assert response.status_code == 200, response.text

    # Đường CÔNG KHAI: SKU đã tắt không được kéo sản phẩm lên nữa.
    after = client.get("/api/products", params={"q": "SKU-AN-DA-TAT"}).json()
    assert after["total"] == 0, (
        f"tìm công khai khớp SKU ĐÃ TẮT — total phải là 0, đang là {after['total']}"
    )
    assert after["items"] == []

    # SKU còn bán vẫn tìm được ⇒ bản vá không chặn nhầm cả nhánh SKU.
    assert client.get("/api/products", params={"q": "SKU-CON-BAN"}).json()["total"] == 1

    # Đường QUẢN TRỊ phải GIỮ NGUYÊN khả năng thấy hàng đã tắt (bật lại được).
    admin = client.get("/api/admin/products", headers=staff_headers).json()
    assert admin["total"] == 1
    admin_skus = {v["sku"]: v["active"] for v in admin["items"][0]["variants"]}
    assert admin_skus == {"SKU-AN-DA-TAT": False, "SKU-CON-BAN": True}, admin_skus


def test_filter_by_category(client, staff_headers):
    _create_product(client, staff_headers)
    other = _create_product(
        client, staff_headers, name="Cáp sạc", slug="cap-sac", category_code="CABLE"
    )
    _create_variant(client, staff_headers, other["product_id"], sku="CABLE-01")

    cases = client.get("/api/products", params={"category": "CASE"}).json()
    assert cases["total"] == 1 and cases["items"][0]["slug"] == PRODUCT_PAYLOAD["slug"]

    cables = client.get("/api/products", params={"category": "cable"}).json()
    assert cables["total"] == 1, "category phải nhận cả chữ thường"


def test_pagination_total_and_page_size_cap(client, staff_headers):
    for index in range(3):
        _create_product(
            client,
            staff_headers,
            name=f"Ốp {index}",
            slug=f"op-{index}",
        )

    page = client.get("/api/products", params={"page_size": 2}).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["page_size"] == 2

    second = client.get("/api/products", params={"page_size": 2, "page": 2}).json()
    assert len(second["items"]) == 1

    over = client.get("/api/products", params={"page_size": 101})
    assert over.status_code == 422, "page_size vượt trần phải 422, không lặng lẽ cắt xuống"

    bad_page = client.get("/api/products", params={"page": 0})
    assert bad_page.status_code == 422


def test_public_categories_endpoint(client):
    body = client.get("/api/catalog/categories").json()
    codes = [item["code"] for item in body]
    assert len(codes) == 10
    assert codes[0] == "CASE", "thứ tự phải theo sort_order"


# ==========================================================================
# Ràng buộc xoá
# ==========================================================================
def test_category_with_products_cannot_be_deleted(db, client, staff_headers):
    """RESTRICT: xoá category còn sản phẩm là phá dữ liệu — DB phải chặn."""
    _create_product(client, staff_headers)
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM categories WHERE code = 'CASE'"))
        db.flush()
    db.rollback()


# ==========================================================================
# Ranh giới xác thực — MỌI route quản trị, không ngoại lệ kể cả route chỉ đọc
# ==========================================================================
def test_every_admin_catalog_route_requires_staff(client, staff_headers):
    created = _create_product(client, staff_headers)
    uuid_str = created["product_id"]

    probes = [
        ("GET", "/api/admin/products", None),
        ("POST", "/api/admin/products", {}),
        ("GET", f"/api/admin/products/{uuid_str}", None),
        ("PATCH", f"/api/admin/products/{uuid_str}", {}),
        ("POST", f"/api/admin/products/{uuid_str}/variants", {}),
        ("PATCH", "/api/admin/variants/OP-VIP-01", {}),
        ("POST", "/api/admin/variants/OP-VIP-01/compatibility", {}),
        ("DELETE", "/api/admin/variants/OP-VIP-01/compatibility/1", None),
    ]
    for method, path, payload in probes:
        kwargs = {"json": payload} if payload is not None else {}
        anonymous = client.request(method, path, **kwargs)
        assert anonymous.status_code in (401, 403, 503), (
            f"{method} {path} trả {anonymous.status_code} khi KHÔNG có khoá — route đang mở!"
        )

        wrong = client.request(method, path, headers={"X-Staff-Key": "sai-khoa"}, **kwargs)
        assert wrong.status_code == 401, f"{method} {path} trả {wrong.status_code} với khoá SAI"

    # Đối chứng dương: có khoá đúng thì đọc được (nếu không, test trên vô nghĩa).
    ok = client.get("/api/admin/products", headers=staff_headers)
    assert ok.status_code == 200


def test_catalog_page_requires_no_auth(client):
    """Đối chứng dương cho ranh giới: ba đường công khai PHẢI mở."""
    assert client.get("/api/products").status_code == 200
    assert client.get("/api/products/khong-ton-tai").status_code == 404
    assert client.get("/api/catalog/categories").status_code == 200


# ==========================================================================
# UI
# ==========================================================================
def test_shop_and_product_pages_are_served_without_inline_code(client):
    for path in ("/shop", "/product/op-bat-ky"):
        response = client.get(path)
        assert response.status_code == 200, f"{path} -> {response.status_code}"
        html = response.text
        assert '<html lang="vi"' in html
        assert 'name="viewport"' in html
        assert "onclick=" not in html and "onsubmit=" not in html, "có inline handler"
        assert 'style="' not in html, "có style nội tuyến — CSP sẽ chặn"
        # Thẻ script phải là file ngoài, không có nội dung nội tuyến.
        for chunk in html.split("<script")[1:]:
            head = chunk.split(">", 1)[0]
            # Đường dẫn TUYỆT ĐỐI từ gốc: `/product/{slug}` là hai tầng, nên
            # `assets/js/x.js` sẽ bị trình duyệt hiểu thành
            # `/product/assets/js/x.js` và 404 — lỗi CHỈ trình duyệt thật bắt được
            # (đã dính đúng lỗi này, xem MASTER_STATUS §36).
            assert 'src="/assets/js/' in head, f"script không phải file ngoài/đường dẫn gốc: {head}"
        assert 'href="/assets/css/styles.css"' in html


def test_shop_page_has_no_hard_coded_products(client):
    """Sản phẩm đi từ API. HTML không được nhắc tên sản phẩm/thương hiệu nào."""
    html = client.get("/shop").text
    for leaked in ("Ốp lưng", "Cáp sạc", "iPhone 1", "250000"):
        assert leaked not in html, f"HTML hard-code dữ liệu: {leaked!r}"


# ==========================================================================
# ĐỐI CHỨNG ÂM TRONG BỘ TEST — chứng minh phép đo PHÂN BIỆT ĐƯỢC
# ==========================================================================
def test_NEGATIVE_control_float_really_loses_money_precision():
    """Chứng minh test giá là phép đo THẬT: `float` sai, `Decimal` đúng.

    Nếu `float` cũng cho kết quả đúng thì test "giá chính xác" ở trên chẳng đo
    được gì cả. Đây là đối chứng cho luật "TIỀN không dùng float".
    """
    float_total = 0.0
    for _ in range(10):
        float_total += 0.1
    assert float_total != 1.0, "float không còn sai số — hằng số này đã đổi, xem lại phép đo"

    decimal_total = sum([Decimal("0.1")] * 10)
    assert decimal_total == Decimal("1.0")


def test_NEGATIVE_control_unfiltered_query_WOULD_show_inactive(client, staff_headers, db):
    """Phá bộ lọc `active` bằng chính truy vấn thô ⇒ thấy hàng đã tắt.

    Chứng minh `Product.active` CHÍNH LÀ thứ đang ẩn hàng đi, chứ không phải
    "tình cờ không có dữ liệu".
    """
    created = _create_product(client, staff_headers)
    client.patch(
        f"/api/admin/products/{created['product_id']}",
        json={"active": False},
        headers=staff_headers,
    )

    assert client.get("/api/products").json()["total"] == 0

    # Cùng dữ liệu, bỏ điều kiện `active`:
    unfiltered = db.execute(select(Product).where(Product.slug == PRODUCT_PAYLOAD["slug"])).scalar()
    assert unfiltered is not None, "không có dòng nào — test đang vô nghĩa"
    assert unfiltered.active is False


def test_NEGATIVE_control_duplicate_sku_is_what_unique_index_blocks(client, staff_headers, db):
    """Chứng minh test UNIQUE là phép đo thật: cùng SKU, DB ném `IntegrityError`."""
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"], sku="OP-DUP-CTRL")

    product = db.execute(
        select(Product).where(Product.slug == PRODUCT_PAYLOAD["slug"])
    ).scalar_one()
    db.add(
        ProductVariant(
            sku="OP-DUP-CTRL",
            product_id=product.id,
            variant_name="Cố tình trùng",
            sale_price=Decimal("1.00"),
            currency="VND",
            active=True,
            stock_tracking=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_NEGATIVE_control_join_would_duplicate_but_exists_does_not(client, staff_headers, db):
    """Chứng minh test chống nhân bản dòng là phép đo THẬT.

    Chạy đúng một `JOIN` (cách SAI) và đúng một `EXISTS` (cách đang dùng) trên
    cùng dữ liệu: `JOIN` ra 3 dòng, `EXISTS` ra 1. Nếu hai cách cho cùng kết quả
    thì test chống nhân bản chẳng đo được gì.
    """
    created = _create_product(client, staff_headers)
    for index in range(3):
        sku = f"OP-JOIN-{index}"
        _create_variant(client, staff_headers, created["product_id"], sku=sku)
        _add_compatibility(client, staff_headers, sku, "iphone-16-pro-max")

    joined = db.execute(
        text(
            """
            SELECT count(*) FROM products p
            JOIN product_variants v ON v.product_id = p.id
            JOIN device_compatibility dc ON dc.sku_id = v.id
            WHERE p.slug = :slug AND dc.device_model_code = 'iphone-16-pro-max'
            """
        ),
        {"slug": PRODUCT_PAYLOAD["slug"]},
    ).scalar_one()
    assert joined == 3, "JOIN phải nhân bản — nếu không, phép đo không còn phân biệt được"

    from app.services.catalog import ProductFilters, count_products

    assert count_products(db, ProductFilters(device_model="iphone-16-pro-max")) == 1


def test_NEGATIVE_control_device_filter_query_path_discriminates(db, client, staff_headers):
    """Đối chứng âm cho lọc theo thiết bị — đo QUA ĐƯỜNG TRUY VẤN THẬT.

    V10 — VÌ SAO PHẢI VIẾT LẠI: bản cũ tên là `..._compatibility_rows_really_exist`
    nhưng chỉ khẳng định có dòng trong `device_compatibility`. Nó KHÔNG đi qua
    `product_query`, nên khi phá bỏ nhánh lọc theo thiết bị thì nó **vẫn XANH** —
    một "đối chứng âm" không phân biệt được gì, đúng thứ mà CLAUDE.md §12.1 gọi là
    "thứ dùng để kiểm chứng lại tự nó không trung thực".

    Bản này giữ lại phần tiền đề (dòng khai báo CÓ thật, để con số 0 bên dưới không
    phải do DB rỗng) rồi ĐO QUA `count_products` — chính hàm dựng truy vấn của
    đường công khai:

    - khớp mã đã khai ⇒ 1
    - KHÔNG khớp mã nào ⇒ 0   ← phá nhánh `_compatible_exists` là vế này ĐỎ (ra 1)
    - không lọc thiết bị ⇒ 1  ← chốt con số 0 ở trên là do LỌC, không do thiếu dữ liệu
    """
    created = _create_product(client, staff_headers)
    _create_variant(client, staff_headers, created["product_id"])
    _add_compatibility(client, staff_headers, "OP-VIP-01", "iphone-16-pro-max")

    rows = db.execute(select(DeviceCompatibility)).scalars().all()
    assert len(rows) == 1, "tiền đề sai: phải có ĐÚNG một dòng khai báo tương thích"
    assert rows[0].device_model_code == "iphone-16-pro-max", (
        "khoá join phải là MÃ máy, không phải tên hiển thị"
    )

    from app.services.catalog import ProductFilters, count_products

    assert count_products(db, ProductFilters(device_model="iphone-16-pro-max")) == 1
    assert count_products(db, ProductFilters(device_model="iphone-khong-co-that")) == 0, (
        "lọc theo máy KHÔNG khớp mà vẫn ra sản phẩm — nhánh lọc đã hỏng"
    )
    assert count_products(db, ProductFilters()) == 1, (
        "không lọc gì mà cũng ra 0 ⇒ con số 0 ở trên là do DB rỗng, không phải do lọc"
    )
