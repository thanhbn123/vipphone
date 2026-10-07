"""Lịch sử giá. Thiết kế: `docs/price-history.md`.

Bắt buộc của gate: đổi giá tạo ĐÚNG MỘT dòng lịch sử · đổi giá thất bại tạo 0 dòng ·
ảnh chụp giá trong đơn cũ không đổi · admin xem được lịch sử.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.test_commerce import add, checkout_body, key, make_sku, new_cart

pytestmark = pytest.mark.integration

SKU = "KINH-01"


def history(client, staff_headers, sku=SKU) -> list[dict]:
    r = client.get(f"/api/admin/variants/{sku}/price-history", headers=staff_headers)
    assert r.status_code == 200, r.text
    return r.json()


def rows(db) -> int:
    return db.execute(text("SELECT count(*) FROM price_history")).scalar_one()


def patch(client, staff_headers, body, sku=SKU):
    return client.patch(f"/api/admin/variants/{sku}", json=body, headers=staff_headers)


def test_creation_records_initial_price_with_actor(client, staff_headers):
    make_sku(client, staff_headers, price="150000.00")
    h = history(client, staff_headers)
    assert [(r["old_price"], r["new_price"], r["reason"]) for r in h] == [
        (None, "150000.00", "Tạo SKU")
    ]
    assert h[0]["changed_by"].startswith("staff:")


def test_price_update_creates_exactly_one_history_row(client, staff_headers, db):
    make_sku(client, staff_headers, price="150000.00")
    before = rows(db)
    r = patch(
        client, staff_headers, {"sale_price": "160000.00", "price_change_reason": "Tăng giá nhập"}
    )
    assert r.status_code == 200, r.text
    assert rows(db) == before + 1
    last = history(client, staff_headers)[-1]
    assert (last["old_price"], last["new_price"], last["reason"]) == (
        "150000.00",
        "160000.00",
        "Tăng giá nhập",
    )
    assert last["changed_by"].startswith("staff:")


def test_non_price_update_creates_no_history(client, staff_headers, db):
    make_sku(client, staff_headers)
    before = rows(db)
    assert (
        patch(client, staff_headers, {"variant_name": "Tên mới", "active": False}).status_code
        == 200
    )
    assert patch(client, staff_headers, {"sale_price": "150000.00"}).status_code == 200  # cùng giá
    assert rows(db) == before


def test_failed_update_creates_no_history(client, staff_headers, db):
    make_sku(client, staff_headers, price="150000.00")
    client.patch(
        f"/api/admin/variants/{SKU}", json={"compare_at_price": "200000.00"}, headers=staff_headers
    )
    before = rows(db)
    # Giá bán mới VƯỢT giá gạch ⇒ 422 ⇒ không có dòng lịch sử, giá giữ nguyên.
    r = patch(client, staff_headers, {"sale_price": "250000.00"})
    assert r.status_code == 422
    assert rows(db) == before
    current = db.execute(text("SELECT sale_price FROM product_variants")).scalar_one()
    assert current == Decimal("150000.00")
    # Giá âm ⇒ 422 ở tầng lược đồ.
    assert patch(client, staff_headers, {"sale_price": "-1"}).status_code == 422
    assert rows(db) == before


def test_rolled_back_db_update_leaves_no_history(db, client, staff_headers):
    make_sku(client, staff_headers)
    before = rows(db)
    db.execute(text("UPDATE product_variants SET sale_price = 1"))
    assert rows(db) == before + 1  # cùng giao dịch: trigger đã ghi
    db.rollback()
    assert rows(db) == before  # rollback ⇒ vết cũng biến mất (nguyên tử)


def test_direct_sql_change_is_still_recorded(db, client, staff_headers):
    make_sku(client, staff_headers)
    db.execute(text("UPDATE product_variants SET sale_price = 99.00"))
    db.commit()
    last = db.execute(
        text("SELECT old_price, new_price, changed_by FROM price_history ORDER BY id DESC LIMIT 1")
    ).one()
    assert (last.old_price, last.new_price) == (Decimal("150000.00"), Decimal("99.00"))
    assert last.changed_by.startswith("db:")


def test_actor_context_does_not_leak_between_transactions(db, client, staff_headers):
    make_sku(client, staff_headers)
    patch(client, staff_headers, {"sale_price": "1.00", "price_change_reason": "lý do A"})
    db.execute(text("UPDATE product_variants SET sale_price = 2.00"))
    db.commit()
    last = db.execute(
        text("SELECT changed_by, reason FROM price_history ORDER BY id DESC LIMIT 1")
    ).one()
    assert last.changed_by.startswith("db:")
    assert last.reason is None


def test_order_snapshot_unchanged_after_price_change(client, staff_headers, db):
    make_sku(client, staff_headers, price="150000.00")
    cart_id, headers = new_cart(client)
    add(client, cart_id, headers, SKU, 2)
    order = client.post(
        "/api/checkout", json=checkout_body(cart_id), headers={**headers, "Idempotency-Key": key()}
    ).json()
    for price in ("170000.00", "90000.00"):
        assert patch(client, staff_headers, {"sale_price": price}).status_code == 200
    item = db.execute(text("SELECT unit_price, line_total FROM order_items")).one()
    assert (item.unit_price, item.line_total) == (Decimal("150000.00"), Decimal("300000.00"))
    detail = client.get(f"/api/admin/orders/{order['order_id']}", headers=staff_headers).json()
    assert detail["grand_total"] == "300000.00"
    assert [h["new_price"] for h in history(client, staff_headers)] == [
        "150000.00",
        "170000.00",
        "90000.00",
    ]


def test_price_history_requires_staff(client, staff_headers):
    make_sku(client, staff_headers)
    assert client.get(f"/api/admin/variants/{SKU}/price-history").status_code == 401


def test_price_history_never_public(client, staff_headers):
    make_sku(client, staff_headers)
    body = str(client.get("/api/products/sp-kinh-01").json())
    assert "old_price" not in body and "changed_by" not in body


def test_update_setting_same_price_records_nothing(db, client, staff_headers):
    """`SET sale_price = sale_price` (giá không đổi) KHÔNG sinh dòng lịch sử.

    Phải đo bằng SQL trực tiếp: qua ORM, SQLAlchemy không gửi UPDATE khi giá trị
    không đổi, nên điều kiện `IS NOT DISTINCT FROM` của trigger không bao giờ bị
    chạm — đối chứng âm đã cho thấy đúng lỗ hổng đó của bộ test.
    """
    make_sku(client, staff_headers)
    before = rows(db)
    db.execute(text("UPDATE product_variants SET sale_price = sale_price, variant_name = 'x'"))
    db.commit()
    assert rows(db) == before
