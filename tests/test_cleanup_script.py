"""`scripts/cleanup_test_data.py` — dọn ĐÚNG dữ liệu có marker, giữ nguyên dữ liệu thật.

Dựng một database có CẢ dữ liệu test (marker) lẫn dữ liệu "thật" (không marker),
chạy script, rồi khẳng định: chế độ đếm không xoá gì · `--apply` chỉ xoá dòng
marker · dữ liệu thật còn nguyên · sổ kho vẫn khớp số dư · từ chối production.
"""

from __future__ import annotations

import importlib.util

import pytest
from sqlalchemy import text

from app.config import REPO_ROOT
from tests.conftest import TEST_DATABASE_URL
from tests.test_commerce import add, checkout_body, key, new_cart
from tests.test_inventory import ledger_matches_balances, move

pytestmark = pytest.mark.integration

spec = importlib.util.spec_from_file_location(
    "cleanup_test_data", REPO_ROOT / "scripts" / "cleanup_test_data.py"
)
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


def product(client, staff_headers, slug, sku, tracked=False):
    pid = client.post(
        "/api/admin/products",
        json={"name": slug, "slug": slug, "category_code": "CABLE"},
        headers=staff_headers,
    ).json()["product_id"]
    client.post(
        f"/api/admin/products/{pid}/variants",
        json={"sku": sku, "variant_name": "x", "sale_price": "10.00", "stock_tracking": tracked},
        headers=staff_headers,
    )
    if tracked:
        move(client, staff_headers, sku, "OPENING", 10)


def buy(client, sku, phone, attribution=None):
    cart_id, headers = new_cart(client)
    add(client, cart_id, headers, sku)
    body = checkout_body(cart_id, attribution=attribution)
    body["customer"]["phone"] = phone
    body["shipping"]["phone"] = phone
    r = client.post("/api/checkout", json=body, headers={**headers, "Idempotency-Key": key()})
    assert r.status_code == 201, r.text


def lead(client, phone, **extra):
    r = client.post(
        "/api/leads",
        json={"full_name": "K", "phone": phone, "iphone_model": "iphone-16-pro-max", "consent": True, **extra},
    )
    assert r.status_code == 201, r.text


@pytest.fixture
def mixed(client, staff_headers):
    product(client, staff_headers, "cap-that", "CAP-THAT", tracked=True)
    product(client, staff_headers, "demo-staging-cap", "DEMO-CAP")
    # Dữ liệu THẬT.
    lead(client, "0911111111", source="bni")
    buy(client, "CAP-THAT", "0911111111", {"source": "bni"})
    # Dữ liệu TEST.
    lead(client, "0900000001", source="staging-test")
    buy(client, "CAP-THAT", "0900000001", {"source": "staging-test"})  # giữ 1 trên SKU thật
    buy(client, "DEMO-CAP", "0900000001", {"utm_campaign": "staging-acceptance"})


def counts(db) -> dict[str, int]:
    tables = ("leads", "orders", "customers", "products", "payments", "order_items")
    return {t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in tables}


def test_count_mode_deletes_nothing(mixed, db, capsys):
    before = counts(db)
    assert cleanup.main(["--database-url", TEST_DATABASE_URL]) == 0
    assert counts(db) == before
    out = capsys.readouterr().out
    assert "CHẾ ĐỘ CHỈ ĐẾM" in out
    assert "orders" in out and "products (demo)" in out


def test_apply_removes_only_marked_and_keeps_ledger_consistent(mixed, db, client, staff_headers):
    assert cleanup.main(["--database-url", TEST_DATABASE_URL, "--apply"]) == 0
    db.expire_all()
    assert counts(db) == {
        "leads": 1,
        "orders": 1,
        "customers": 1,
        "products": 1,
        "payments": 1,
        "order_items": 1,
    }
    assert db.execute(text("SELECT phone FROM leads")).scalar_one() == "0911111111"
    assert db.execute(text("SELECT source FROM orders")).scalar_one() == "bni"
    assert db.execute(text("SELECT slug FROM products")).scalar_one() == "cap-that"
    # SKU thật: đơn thật còn giữ 1; phần đơn test giữ đã được NHẢ bằng một dòng RELEASE.
    bal = db.execute(
        text("SELECT quantity_on_hand, quantity_reserved FROM inventory_balances")
    ).one()
    assert tuple(bal) == (10, 1)
    assert ledger_matches_balances(db)
    released = db.execute(
        text("SELECT count(*) FROM inventory_movements WHERE actor = 'cleanup:test-data'")
    ).scalar_one()
    assert released == 1
    # Chạy lại: không còn gì.
    assert cleanup.main(["--database-url", TEST_DATABASE_URL, "--apply"]) == 0


def test_customer_with_any_real_activity_is_kept(client, staff_headers, db):
    product(client, staff_headers, "cap-that", "CAP-THAT")
    lead(client, "0922222222", source="staging-test")
    buy(client, "CAP-THAT", "0922222222", {"source": "facebook"})  # đơn THẬT của cùng khách
    assert cleanup.main(["--database-url", TEST_DATABASE_URL, "--apply"]) == 0
    db.expire_all()
    assert db.execute(text("SELECT count(*) FROM customers")).scalar_one() == 1
    assert db.execute(text("SELECT count(*) FROM orders")).scalar_one() == 1
    assert db.execute(text("SELECT count(*) FROM leads")).scalar_one() == 0


def test_demo_product_in_real_order_is_kept(client, staff_headers, db):
    product(client, staff_headers, "demo-staging-cap", "DEMO-CAP")
    buy(client, "DEMO-CAP", "0933333333", {"source": "zalo"})
    assert cleanup.main(["--database-url", TEST_DATABASE_URL, "--apply"]) == 0
    db.expire_all()
    assert db.execute(text("SELECT count(*) FROM products")).scalar_one() == 1


def test_refuses_production(monkeypatch, capsys):
    monkeypatch.setenv("APP_ENV", "production")
    assert cleanup.main(["--database-url", TEST_DATABASE_URL, "--apply"]) == 2
    assert "TỪ CHỐI" in capsys.readouterr().err


def test_refuses_prod_named_database(capsys):
    url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/vipphone_prod"
    assert cleanup.main(["--database-url", url, "--apply"]) == 2
