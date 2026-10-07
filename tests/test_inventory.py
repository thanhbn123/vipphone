"""Kho tối giản. Thiết kế: `docs/inventory.md`.

Bảo vệ: available = on_hand - reserved · checkout không bán vượt (kể cả đồng
thời) · huỷ nhả hàng · giao đi trừ kho · điều chỉnh tay có vết + lý do · sổ cái
khớp số dư · con số tồn KHÔNG lộ ra đường công khai.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.test_commerce import add, checkout_body, key, make_sku, new_cart

pytestmark = pytest.mark.integration

SKU = "KINH-01"


def tracked_sku(client, staff_headers, *, opening: int | None = 3, sku=SKU) -> str:
    make_sku(client, staff_headers, sku=sku)
    r = client.patch(
        f"/api/admin/variants/{sku}", json={"stock_tracking": True}, headers=staff_headers
    )
    assert r.status_code == 200, r.text
    if opening is not None:
        move(client, staff_headers, sku, "OPENING", opening)
    return sku


def move(client, staff_headers, sku, kind, quantity, reason=None, expect=201):
    r = client.post(
        f"/api/admin/inventory/{sku}/movements",
        json={"movement_type": kind, "quantity": quantity, "reason": reason},
        headers=staff_headers,
    )
    assert r.status_code == expect, r.text
    return r.json()


def balance(client, staff_headers, sku=SKU) -> tuple[int, int, int]:
    b = client.get(f"/api/admin/inventory/{sku}", headers=staff_headers).json()["balance"]
    return b["quantity_on_hand"], b["quantity_reserved"], b["quantity_available"]


def buy(client, sku=SKU, quantity=1):
    cart_id, headers = new_cart(client)
    assert add(client, cart_id, headers, sku, quantity).status_code == 200
    return client.post(
        "/api/checkout", json=checkout_body(cart_id), headers={**headers, "Idempotency-Key": key()}
    )


def set_status(client, staff_headers, order_id, *statuses):
    for status in statuses:
        r = client.post(
            f"/api/admin/orders/{order_id}/status",
            json={"to_status": status},
            headers=staff_headers,
        )
        assert r.status_code == 200, r.text


def ledger_matches_balances(db: Session) -> bool:
    mismatches = db.execute(
        text(
            "SELECT count(*) FROM inventory_balances b LEFT JOIN ("
            "  SELECT sku_id, sum(delta_on_hand) oh, sum(delta_reserved) rs "
            "  FROM inventory_movements GROUP BY sku_id) m ON m.sku_id = b.sku_id "
            "WHERE b.quantity_on_hand <> coalesce(m.oh, 0) "
            "   OR b.quantity_reserved <> coalesce(m.rs, 0)"
        )
    ).scalar_one()
    return mismatches == 0


# --------------------------------------------------------------------------
# Số dư + thao tác tay
# --------------------------------------------------------------------------
def test_opening_receipt_adjustment_and_available_formula(client, staff_headers, db):
    tracked_sku(client, staff_headers, opening=10)
    move(client, staff_headers, SKU, "RECEIPT", 5)
    move(client, staff_headers, SKU, "ADJUSTMENT", -2, reason="Kiểm kê thiếu 2")
    assert balance(client, staff_headers) == (13, 0, 13)
    detail = client.get(f"/api/admin/inventory/{SKU}", headers=staff_headers).json()
    assert [(m["movement_type"], m["delta_on_hand"]) for m in detail["movements"]] == [
        ("OPENING", 10),
        ("RECEIPT", 5),
        ("ADJUSTMENT", -2),
    ]
    assert all(m["actor"].startswith("staff:") for m in detail["movements"])
    assert detail["movements"][2]["reason"] == "Kiểm kê thiếu 2"
    assert ledger_matches_balances(db)


def test_available_is_generated_column(db, client, staff_headers):
    from sqlalchemy.exc import DBAPIError

    tracked_sku(client, staff_headers)
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE inventory_balances SET quantity_available = 999"))
        db.flush()
    db.rollback()


def test_adjustment_requires_reason_and_cannot_go_negative(client, staff_headers, db):
    tracked_sku(client, staff_headers, opening=2)
    move(client, staff_headers, SKU, "ADJUSTMENT", -1, expect=422)
    move(client, staff_headers, SKU, "ADJUSTMENT", -5, reason="sai", expect=409)
    move(client, staff_headers, SKU, "ADJUSTMENT", 0, reason="x", expect=422)
    move(client, staff_headers, SKU, "RECEIPT", -1, expect=422)
    move(client, staff_headers, SKU, "RETURN", 1, expect=422)
    assert balance(client, staff_headers) == (2, 0, 2)
    assert ledger_matches_balances(db)


def test_opening_only_once(client, staff_headers):
    tracked_sku(client, staff_headers, opening=1)
    r = client.post(
        f"/api/admin/inventory/{SKU}/movements",
        json={"movement_type": "OPENING", "quantity": 5},
        headers=staff_headers,
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "OPENING_ALREADY_RECORDED"


def test_staff_cannot_write_order_movement_types(client, staff_headers):
    tracked_sku(client, staff_headers)
    for kind in ("RESERVE", "RELEASE", "SALE"):
        move(client, staff_headers, SKU, kind, 1, expect=422)


def test_adjustment_cannot_drop_below_reserved(client, staff_headers, db):
    tracked_sku(client, staff_headers, opening=3)
    assert buy(client, quantity=2).status_code == 201
    move(client, staff_headers, SKU, "ADJUSTMENT", -2, reason="mất", expect=409)
    assert balance(client, staff_headers) == (3, 2, 1)


def test_db_rejects_invariant_violation(db, client, staff_headers):
    from sqlalchemy.exc import IntegrityError

    tracked_sku(client, staff_headers, opening=1)
    for sql in (
        "UPDATE inventory_balances SET quantity_on_hand = -1, quantity_reserved = 0",
        "UPDATE inventory_balances SET quantity_reserved = quantity_on_hand + 1",
    ):
        with pytest.raises(IntegrityError):
            db.execute(text(sql))
            db.flush()
        db.rollback()


# --------------------------------------------------------------------------
# Đơn hàng: giữ, nhả, bán
# --------------------------------------------------------------------------
def test_checkout_reserves_and_blocks_oversell(client, staff_headers, db):
    tracked_sku(client, staff_headers, opening=3)
    assert buy(client, quantity=2).status_code == 201
    assert balance(client, staff_headers) == (3, 2, 1)
    r = buy(client, quantity=2)
    assert r.status_code == 409 and r.json()["error"]["code"] == "OUT_OF_STOCK"
    assert r.json()["error"]["fields"]["skus"] == SKU
    assert db.execute(text("SELECT count(*) FROM orders")).scalar_one() == 1
    # Hết hàng ⇒ không có khoản thu "mồ côi" nào cho đơn không thành.
    assert db.execute(text("SELECT count(*) FROM payments")).scalar_one() == 1
    assert buy(client, quantity=1).status_code == 201
    assert balance(client, staff_headers) == (3, 3, 0)


def test_tracked_sku_without_ledger_is_out_of_stock(client, staff_headers, db):
    tracked_sku(client, staff_headers, opening=None)
    r = buy(client)
    assert r.status_code == 409 and r.json()["error"]["code"] == "OUT_OF_STOCK"


def test_untracked_sku_is_not_limited(client, staff_headers, db):
    make_sku(client, staff_headers, sku="CAP-01")
    for _ in range(3):
        assert buy(client, sku="CAP-01", quantity=5).status_code == 201
    assert db.execute(text("SELECT count(*) FROM inventory_movements")).scalar_one() == 0


def test_cancel_releases_reservation(client, staff_headers, db):
    tracked_sku(client, staff_headers, opening=3)
    order = buy(client, quantity=2).json()
    set_status(client, staff_headers, order["order_id"], "CANCELLED")
    assert balance(client, staff_headers) == (3, 0, 3)
    # Huỷ hai lần không thể — trạng thái cuối. Không nhả hai lần.
    r = client.post(
        f"/api/admin/orders/{order['order_id']}/status",
        json={"to_status": "CANCELLED"},
        headers=staff_headers,
    )
    assert r.status_code == 409
    assert balance(client, staff_headers) == (3, 0, 3)
    assert ledger_matches_balances(db)


def test_shipping_converts_reservation_to_sale(client, staff_headers, db):
    tracked_sku(client, staff_headers, opening=3)
    order = buy(client, quantity=2).json()
    set_status(client, staff_headers, order["order_id"], "CONFIRMED", "PROCESSING")
    assert balance(client, staff_headers) == (3, 2, 1)
    set_status(client, staff_headers, order["order_id"], "SHIPPED")
    assert balance(client, staff_headers) == (1, 0, 1)
    detail = client.get(f"/api/admin/inventory/{SKU}", headers=staff_headers).json()
    assert [
        (m["movement_type"], m["delta_on_hand"], m["delta_reserved"], m["order_number"])
        for m in detail["movements"]
    ] == [
        ("OPENING", 3, 0, None),
        ("RESERVE", 0, 2, order["order_number"]),
        ("SALE", -2, -2, order["order_number"]),
    ]
    set_status(client, staff_headers, order["order_id"], "COMPLETED")
    assert balance(client, staff_headers) == (1, 0, 1)
    move(client, staff_headers, SKU, "RETURN", 1, reason="Khách trả lại")
    assert balance(client, staff_headers) == (2, 0, 2)
    assert ledger_matches_balances(db)


def test_public_availability_follows_stock_but_hides_numbers(client, staff_headers):
    tracked_sku(client, staff_headers, opening=1)
    slug = "sp-kinh-01"
    assert client.get(f"/api/products/{slug}").json()["availability"] == "IN_STOCK"
    assert buy(client).status_code == 201
    body = client.get(f"/api/products/{slug}").json()
    assert body["availability"] == "OUT_OF_STOCK"
    text_body = str(body)
    for field in ("quantity_on_hand", "quantity_reserved", "quantity_available"):
        assert field not in text_body


def test_inventory_admin_requires_staff(client, staff_headers):
    tracked_sku(client, staff_headers)
    assert client.get("/api/admin/inventory").status_code == 401
    assert client.get(f"/api/admin/inventory/{SKU}").status_code == 401
    r = client.post(
        f"/api/admin/inventory/{SKU}/movements", json={"movement_type": "RECEIPT", "quantity": 1}
    )
    assert r.status_code == 401


def test_inventory_list_and_low_stock_filter(client, staff_headers):
    tracked_sku(client, staff_headers, opening=1, sku="KINH-01")
    tracked_sku(client, staff_headers, opening=50, sku="KINH-02")
    rows = client.get("/api/admin/inventory", headers=staff_headers).json()
    assert [(r["sku"], r["quantity_available"]) for r in rows] == [("KINH-01", 1), ("KINH-02", 50)]
    low = client.get(
        "/api/admin/inventory", params={"low_stock_below": 5}, headers=staff_headers
    ).json()
    assert [r["sku"] for r in low] == ["KINH-01"]


# --------------------------------------------------------------------------
# Đồng thời — không bán vượt
# --------------------------------------------------------------------------
def test_concurrent_checkouts_never_oversell(engine, client, staff_headers):
    from app.routers.commerce import CHECKOUT_HOOKS
    from app.schemas import CheckoutRequest
    from app.services import commerce

    tracked_sku(client, staff_headers, opening=3)
    carts = []
    for _ in range(10):
        cart_id, headers = new_cart(client)
        add(client, cart_id, headers, SKU, 1)
        carts.append((cart_id, headers["X-Cart-Token"]))

    barrier = threading.Barrier(len(carts))
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(cart_id, token):
        payload = CheckoutRequest.model_validate(checkout_body(cart_id))
        with Session(engine, expire_on_commit=False) as session:
            barrier.wait()
            try:
                commerce.checkout(
                    session,
                    payload,
                    idempotency_key=uuid.uuid4().hex,
                    token=token,
                    hooks=tuple(CHECKOUT_HOOKS),
                )
                result = "ok"
            except Exception as exc:
                session.rollback()
                result = getattr(exc, "code", type(exc).__name__)
            with lock:
                outcomes.append(result)

    threads = [threading.Thread(target=worker, args=c) for c in carts]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert sorted(outcomes) == ["OUT_OF_STOCK"] * 7 + ["ok"] * 3, outcomes
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT quantity_on_hand, quantity_reserved, quantity_available "
                "FROM inventory_balances"
            )
        ).one()
        assert tuple(row) == (3, 3, 0)
        assert conn.execute(text("SELECT count(*) FROM orders")).scalar_one() == 3
