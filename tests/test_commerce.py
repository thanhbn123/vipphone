"""G16 — Giỏ hàng + đơn hàng. Thiết kế: `docs/commerce.md`.

Bộ test bắt buộc của gate: giả giá · idempotency · checkout đồng thời · sở hữu giỏ ·
IDOR đơn · SKU đã tắt · địa chỉ sai · chuyển trạng thái. `test_NEGATIVE_control_*`
chứng minh phép đo phân biệt được đúng/sai.
"""

from __future__ import annotations

import threading
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

DEVICE = "iphone-16-pro-max"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def make_sku(client, staff_headers, *, sku="KINH-01", price="150000.00", slug=None) -> str:
    slug = slug or f"sp-{sku.lower()}"
    r = client.post(
        "/api/admin/products",
        json={"name": f"Sản phẩm {sku}", "slug": slug, "category_code": "SCREEN_PROTECTOR"},
        headers=staff_headers,
    )
    assert r.status_code == 201, r.text
    r = client.post(
        f"/api/admin/products/{r.json()['product_id']}/variants",
        json={"sku": sku, "variant_name": "Bản thường", "sale_price": price, "cost_price": "1.00"},
        headers=staff_headers,
    )
    assert r.status_code == 201, r.text
    return sku


def new_cart(client) -> tuple[str, dict]:
    r = client.post("/api/cart")
    assert r.status_code == 201, r.text
    body = r.json()
    return body["cart_id"], {"X-Cart-Token": body["cart_token"]}


def add(client, cart_id, headers, sku, quantity=1):
    return client.post(
        f"/api/cart/{cart_id}/items", json={"sku": sku, "quantity": quantity}, headers=headers
    )


def checkout_body(cart_id: str, **overrides) -> dict:
    body = {
        "cart_id": cart_id,
        "customer": {"full_name": "Khách Test", "phone": "0912345678", "email": "a@example.com"},
        "shipping": {
            "recipient_name": "Khách Test",
            "phone": "0912345678",
            "address_line": "12 Đường Số 1, Phường 2",
            "district": "Quận 3",
            "province": "TP Hồ Chí Minh",
        },
    }
    body.update(overrides)
    return body


def key() -> str:
    return uuid.uuid4().hex


def do_checkout(client, cart_id, headers, *, idem=None, **overrides):
    return client.post(
        "/api/checkout",
        json=checkout_body(cart_id, **overrides),
        headers={**headers, "Idempotency-Key": idem or key()},
    )


def order_count(db: Session) -> int:
    return db.execute(text("SELECT count(*) FROM orders")).scalar_one()


@pytest.fixture
def ready_cart(client, staff_headers):
    sku = make_sku(client, staff_headers)
    cart_id, headers = new_cart(client)
    assert add(client, cart_id, headers, sku, 2).status_code == 200
    return cart_id, headers, sku


# --------------------------------------------------------------------------
# Giỏ hàng
# --------------------------------------------------------------------------
def test_cart_create_add_update_remove(client, staff_headers):
    sku = make_sku(client, staff_headers)
    cart_id, headers = new_cart(client)

    body = add(client, cart_id, headers, sku, 2).json()
    assert body["subtotal"] == "300000.00"
    assert [(i["sku"], i["quantity"], i["line_total"]) for i in body["items"]] == [
        (sku, 2, "300000.00")
    ]
    # Thêm lại cùng SKU ⇒ cộng dồn, không tạo dòng thứ hai.
    body = add(client, cart_id, headers, sku, 1).json()
    assert [(i["sku"], i["quantity"]) for i in body["items"]] == [(sku, 3)]

    r = client.patch(f"/api/cart/{cart_id}/items/{sku}", json={"quantity": 5}, headers=headers)
    assert r.json()["subtotal"] == "750000.00"

    r = client.delete(f"/api/cart/{cart_id}/items/{sku}", headers=headers)
    assert r.json()["items"] == [] and r.json()["subtotal"] == "0.00"

    assert client.get(f"/api/cart/{cart_id}", headers=headers).status_code == 200


def test_cart_token_is_returned_once_and_only_hash_is_stored(client, db):
    r = client.post("/api/cart")
    token = r.json()["cart_token"]
    stored = db.execute(text("SELECT owner_token_hash FROM carts")).scalar_one()
    assert token not in stored
    assert len(stored) == 64
    assert (
        "cart_token"
        not in client.get(
            f"/api/cart/{r.json()['cart_id']}", headers={"X-Cart-Token": token}
        ).json()
    )


def test_quantity_bounds(client, staff_headers):
    sku = make_sku(client, staff_headers)
    cart_id, headers = new_cart(client)
    assert add(client, cart_id, headers, sku, 0).status_code == 422
    assert add(client, cart_id, headers, sku, 100).status_code == 422
    assert add(client, cart_id, headers, sku, 99).status_code == 200
    assert add(client, cart_id, headers, sku, 1).status_code == 422


# --------------------------------------------------------------------------
# Sở hữu giỏ (cart ownership)
# --------------------------------------------------------------------------
def test_cart_requires_owner_token(client, ready_cart):
    cart_id, _headers, sku = ready_cart
    _other_id, other_headers = new_cart(client)
    for headers in ({}, {"X-Cart-Token": "sai"}, other_headers):
        assert client.get(f"/api/cart/{cart_id}", headers=headers).status_code == 404
        assert add(client, cart_id, headers, sku).status_code == 404
        assert (
            client.patch(
                f"/api/cart/{cart_id}/items/{sku}", json={"quantity": 9}, headers=headers
            ).status_code
            == 404
        )
        assert client.delete(f"/api/cart/{cart_id}/items/{sku}", headers=headers).status_code == 404
        assert do_checkout(client, cart_id, headers).status_code == 404


def test_wrong_token_and_missing_cart_are_indistinguishable(client, ready_cart):
    cart_id, _, _ = ready_cart
    wrong = client.get(f"/api/cart/{cart_id}", headers={"X-Cart-Token": "x"}).json()
    missing = client.get(f"/api/cart/{uuid.uuid4()}", headers={"X-Cart-Token": "x"}).json()
    assert wrong == missing


# --------------------------------------------------------------------------
# Giả giá (price tampering)
# --------------------------------------------------------------------------
def test_client_cannot_send_price_fields(client, staff_headers):
    sku = make_sku(client, staff_headers)
    cart_id, headers = new_cart(client)
    r = client.post(
        f"/api/cart/{cart_id}/items",
        json={"sku": sku, "quantity": 1, "unit_price": "1.00"},
        headers=headers,
    )
    assert r.status_code == 422
    assert add(client, cart_id, headers, sku).status_code == 200
    for field in ({"grand_total": "1.00"}, {"subtotal": "1.00"}, {"items": []}):
        r = do_checkout(client, cart_id, headers, **field)
        assert r.status_code == 422, field


def test_server_computes_total_from_db_price(client, ready_cart, db):
    cart_id, headers, _ = ready_cart
    r = do_checkout(client, cart_id, headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["subtotal"], body["shipping_fee"], body["grand_total"]) == (
        "300000.00",
        "0.00",
        "300000.00",
    )
    assert [(i["sku"], i["unit_price"], i["quantity"], i["line_total"]) for i in body["items"]] == [
        ("KINH-01", "150000.00", 2, "300000.00")
    ]


def test_expected_total_mismatch_rejected_without_order(client, ready_cart, db):
    cart_id, headers, _ = ready_cart
    r = do_checkout(client, cart_id, headers, expected_total="1000.00")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PRICE_CHANGED"
    assert order_count(db) == 0
    # Đúng tổng ⇒ đặt được.
    assert do_checkout(client, cart_id, headers, expected_total="300000.00").status_code == 201


def test_price_change_between_view_and_checkout_is_caught(client, staff_headers, ready_cart, db):
    cart_id, headers, sku = ready_cart
    seen = client.get(f"/api/cart/{cart_id}", headers=headers).json()["subtotal"]
    client.patch(
        f"/api/admin/variants/{sku}", json={"sale_price": "160000.00"}, headers=staff_headers
    )
    r = do_checkout(client, cart_id, headers, expected_total=seen)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PRICE_CHANGED"
    assert order_count(db) == 0


# --------------------------------------------------------------------------
# Idempotency + đồng thời
# --------------------------------------------------------------------------
def test_same_key_replays_same_order(client, ready_cart, db):
    cart_id, headers, _ = ready_cart
    idem = key()
    first = do_checkout(client, cart_id, headers, idem=idem)
    second = do_checkout(client, cart_id, headers, idem=idem)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["order_id"] == second.json()["order_id"]
    assert (first.json()["replayed"], second.json()["replayed"]) == (False, True)
    assert order_count(db) == 1


def test_same_key_with_different_body_is_rejected(client, ready_cart, db):
    cart_id, headers, _ = ready_cart
    idem = key()
    assert do_checkout(client, cart_id, headers, idem=idem).status_code == 201
    r = do_checkout(client, cart_id, headers, idem=idem, customer_note="đổi nội dung")
    assert r.status_code == 422 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert order_count(db) == 1


def test_second_key_on_same_cart_does_not_create_second_order(client, ready_cart, db):
    cart_id, headers, _ = ready_cart
    first = do_checkout(client, cart_id, headers)
    second = do_checkout(client, cart_id, headers)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CART_ALREADY_CHECKED_OUT"
    assert second.json()["error"]["fields"]["order_id"] == first.json()["order_id"]
    assert order_count(db) == 1


def test_idempotency_key_required(client, ready_cart, db):
    cart_id, headers, _ = ready_cart
    for bad in (None, "ngan", "x" * 129, "co dau cach va ky tu la!!"):
        h = dict(headers)
        if bad is not None:
            h["Idempotency-Key"] = bad
        r = client.post("/api/checkout", json=checkout_body(cart_id), headers=h)
        assert r.status_code == 400, bad
    assert order_count(db) == 0


def test_another_owners_key_cannot_read_their_order(client, staff_headers, db):
    sku = make_sku(client, staff_headers)
    a_id, a_headers = new_cart(client)
    add(client, a_id, a_headers, sku)
    idem = key()
    assert do_checkout(client, a_id, a_headers, idem=idem).status_code == 201
    b_id, b_headers = new_cart(client)
    add(client, b_id, b_headers, sku)
    r = do_checkout(client, b_id, b_headers, idem=idem)
    assert r.status_code == 409
    assert "order_id" not in r.text
    assert order_count(db) == 1


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_checkout_creates_exactly_one_order(engine, client, ready_cart, same_key):
    """N luồng checkout CÙNG giỏ cùng lúc ⇒ đúng MỘT đơn."""
    from app.schemas import CheckoutRequest
    from app.services import commerce

    cart_id, headers, _ = ready_cart
    token = headers["X-Cart-Token"]
    payload = CheckoutRequest.model_validate(checkout_body(cart_id))
    shared = key()
    barrier = threading.Barrier(8)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker():
        with Session(engine, expire_on_commit=False) as session:
            barrier.wait()
            try:
                result = commerce.checkout(
                    session,
                    payload,
                    idempotency_key=shared if same_key else key(),
                    token=token,
                )
                outcome = f"order:{result.order.order_id}:{result.replayed}"
            except Exception as exc:
                session.rollback()
                outcome = f"error:{getattr(exc, 'code', type(exc).__name__)}"
            with lock:
                outcomes.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM orders")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM order_items")).scalar_one() == 1
    created = [o for o in outcomes if o.startswith("order:") and o.endswith(":False")]
    assert len(created) == 1, outcomes
    if same_key:
        assert all(o.startswith("order:") for o in outcomes), outcomes
        assert len({o.split(":")[1] for o in outcomes}) == 1
    else:
        assert sorted({o for o in outcomes if o.startswith("error")}) == [
            "error:CART_ALREADY_CHECKED_OUT"
        ]


# --------------------------------------------------------------------------
# IDOR đơn hàng
# --------------------------------------------------------------------------
def test_order_lookup_requires_owner_token(client, ready_cart):
    cart_id, headers, _ = ready_cart
    order = do_checkout(client, cart_id, headers).json()
    url = f"/api/orders/{order['order_id']}"
    ok = client.get(url, headers={"X-Order-Token": headers["X-Cart-Token"]})
    assert ok.status_code == 200
    assert ok.json()["order_number"] == order["order_number"]
    assert ok.json()["phone_masked"] == "0912***678"

    _, other = new_cart(client)
    for h in ({}, {"X-Order-Token": "x"}, {"X-Order-Token": other["X-Cart-Token"]}):
        assert client.get(url, headers=h).status_code == 404
    missing = client.get(f"/api/orders/{uuid.uuid4()}", headers={"X-Order-Token": "x"})
    assert missing.json() == client.get(url, headers={"X-Order-Token": "x"}).json()


def test_admin_order_routes_require_staff(client, ready_cart):
    cart_id, headers, _ = ready_cart
    order = do_checkout(client, cart_id, headers).json()
    assert client.get("/api/admin/orders").status_code == 401
    assert client.get(f"/api/admin/orders/{order['order_id']}").status_code == 401
    r = client.post(
        f"/api/admin/orders/{order['order_id']}/status",
        json={"to_status": "CONFIRMED"},
        headers=headers,
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------
# SKU đã tắt
# --------------------------------------------------------------------------
def test_inactive_sku_cannot_be_added(client, staff_headers):
    sku = make_sku(client, staff_headers)
    client.patch(f"/api/admin/variants/{sku}", json={"active": False}, headers=staff_headers)
    cart_id, headers = new_cart(client)
    r = add(client, cart_id, headers, sku)
    assert r.status_code == 404 and r.json()["error"]["code"] == "SKU_NOT_AVAILABLE"


def test_sku_deactivated_after_adding_blocks_checkout(client, staff_headers, ready_cart, db):
    cart_id, headers, sku = ready_cart
    client.patch(f"/api/admin/variants/{sku}", json={"active": False}, headers=staff_headers)
    cart = client.get(f"/api/cart/{cart_id}", headers=headers).json()
    assert (cart["items"][0]["available"], cart["subtotal"]) == (False, "0.00")
    r = do_checkout(client, cart_id, headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "SKU_UNAVAILABLE"
    assert order_count(db) == 0


def test_inactive_product_blocks_add_and_checkout(client, staff_headers, ready_cart, db):
    cart_id, headers, sku = ready_cart
    products = client.get("/api/admin/products", headers=staff_headers).json()["items"]
    client.patch(
        f"/api/admin/products/{products[0]['product_id']}",
        json={"active": False},
        headers=staff_headers,
    )
    assert add(client, cart_id, headers, sku).status_code == 404
    assert do_checkout(client, cart_id, headers).status_code == 409
    assert order_count(db) == 0


def test_empty_cart_cannot_checkout(client, db):
    cart_id, headers = new_cart(client)
    r = do_checkout(client, cart_id, headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "CART_EMPTY"


# --------------------------------------------------------------------------
# Địa chỉ sai
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "shipping_patch, field",
    [
        ({"phone": "12345"}, "phone"),
        ({"phone": "0212345678"}, "phone"),
        ({"address_line": "abc"}, "address_line"),
        ({"address_line": "      "}, "address_line"),
        ({"province": ""}, "province"),
        ({"recipient_name": "   "}, "recipient_name"),
        ({"evil": "x"}, "evil"),
    ],
)
def test_invalid_shipping_address_rejected(client, ready_cart, db, shipping_patch, field):
    cart_id, headers, _ = ready_cart
    body = checkout_body(cart_id)
    body["shipping"] = {**body["shipping"], **shipping_patch}
    r = client.post("/api/checkout", json=body, headers={**headers, "Idempotency-Key": key()})
    assert r.status_code == 422, r.text
    assert field in r.json()["error"]["fields"]
    assert order_count(db) == 0


def test_missing_shipping_rejected(client, ready_cart, db):
    cart_id, headers, _ = ready_cart
    body = checkout_body(cart_id)
    del body["shipping"]
    r = client.post("/api/checkout", json=body, headers={**headers, "Idempotency-Key": key()})
    assert r.status_code == 422
    assert order_count(db) == 0


def test_phone_is_canonicalised_and_customer_reused(client, staff_headers, db):
    sku = make_sku(client, staff_headers)
    for phone in ("+84 912 345 678", "0912345678"):
        cart_id, headers = new_cart(client)
        add(client, cart_id, headers, sku)
        body = checkout_body(cart_id)
        body["customer"]["phone"] = phone
        body["shipping"]["phone"] = phone
        r = client.post("/api/checkout", json=body, headers={**headers, "Idempotency-Key": key()})
        assert r.status_code == 201, r.text
    assert db.execute(text("SELECT count(*) FROM customers")).scalar_one() == 1
    assert db.execute(text("SELECT DISTINCT phone FROM shipping_addresses")).scalars().all() == [
        "0912345678"
    ]


def test_checkout_does_not_grant_marketing_consent(client, ready_cart, db):
    cart_id, headers, _ = ready_cart
    do_checkout(client, cart_id, headers)
    assert db.execute(text("SELECT marketing_consent FROM customers")).scalar_one() is False


# --------------------------------------------------------------------------
# Chuyển trạng thái
# --------------------------------------------------------------------------
def _set(client, staff_headers, order_id, to_status):
    return client.post(
        f"/api/admin/orders/{order_id}/status",
        json={"to_status": to_status, "reason": "test"},
        headers=staff_headers,
    )


def test_full_status_lifecycle_is_recorded(client, staff_headers, ready_cart):
    cart_id, headers, _ = ready_cart
    order_id = do_checkout(client, cart_id, headers).json()["order_id"]
    for status in ("CONFIRMED", "PROCESSING", "SHIPPED", "COMPLETED"):
        r = _set(client, staff_headers, order_id, status)
        assert r.status_code == 200, r.text
    detail = client.get(f"/api/admin/orders/{order_id}", headers=staff_headers).json()
    assert detail["status"] == "COMPLETED"
    assert detail["allowed_transitions"] == []
    status_events = [e for e in detail["events"] if e["field"] == "status"]
    assert [(e["from_value"], e["to_value"]) for e in status_events] == [
        (None, "PENDING_PAYMENT"),
        ("PENDING_PAYMENT", "CONFIRMED"),
        ("CONFIRMED", "PROCESSING"),
        ("PROCESSING", "SHIPPED"),
        ("SHIPPED", "COMPLETED"),
    ]
    assert all(e["actor"].startswith(("staff:", "customer:")) for e in detail["events"])


@pytest.mark.parametrize(
    "path, bad",
    [
        ([], "SHIPPED"),
        ([], "COMPLETED"),
        (["CONFIRMED"], "PENDING_PAYMENT"),
        (["CANCELLED"], "CONFIRMED"),
        (["CONFIRMED", "PROCESSING", "SHIPPED"], "CANCELLED"),
        (["CONFIRMED", "PROCESSING", "SHIPPED", "COMPLETED"], "CANCELLED"),
    ],
)
def test_invalid_transitions_rejected(client, staff_headers, ready_cart, path, bad):
    cart_id, headers, _ = ready_cart
    order_id = do_checkout(client, cart_id, headers).json()["order_id"]
    for status in path:
        assert _set(client, staff_headers, order_id, status).status_code == 200
    before = client.get(f"/api/admin/orders/{order_id}", headers=staff_headers).json()
    r = _set(client, staff_headers, order_id, bad)
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
    after = client.get(f"/api/admin/orders/{order_id}", headers=staff_headers).json()
    assert after["status"] == before["status"] and after["events"] == before["events"]


def test_unknown_status_rejected(client, staff_headers, ready_cart):
    cart_id, headers, _ = ready_cart
    order_id = do_checkout(client, cart_id, headers).json()["order_id"]
    assert _set(client, staff_headers, order_id, "PAID").status_code == 422


def test_db_rejects_unknown_status_and_bad_totals(client, ready_cart, db):
    from sqlalchemy.exc import IntegrityError

    cart_id, headers, _ = ready_cart
    do_checkout(client, cart_id, headers)
    for sql in (
        "UPDATE orders SET status = 'LOST'",
        "UPDATE orders SET grand_total = grand_total + 1",
        "UPDATE order_items SET line_total = line_total + 1",
    ):
        with pytest.raises(IntegrityError):
            db.execute(text(sql))
            db.flush()
        db.rollback()


# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------
def test_admin_list_filter_and_detail(client, staff_headers, ready_cart):
    cart_id, headers, _ = ready_cart
    order = do_checkout(client, cart_id, headers).json()
    page = client.get("/api/admin/orders", headers=staff_headers).json()
    assert page["total"] == 1
    row = page["items"][0]
    assert (row["order_number"], row["status"], row["item_count"], row["phone_masked"]) == (
        order["order_number"],
        "PENDING_PAYMENT",
        2,
        "0912***678",
    )
    assert (
        client.get(
            "/api/admin/orders", params={"status": "COMPLETED"}, headers=staff_headers
        ).json()["total"]
        == 0
    )
    assert (
        client.get(
            "/api/admin/orders", params={"q": order["order_number"]}, headers=staff_headers
        ).json()["total"]
        == 1
    )
    assert (
        client.get("/api/admin/orders", params={"q": "0912345678"}, headers=staff_headers).json()[
            "total"
        ]
        == 1
    )
    detail = client.get(f"/api/admin/orders/{order['order_id']}", headers=staff_headers).json()
    assert detail["shipping"]["phone"] == "0912345678"
    assert detail["allowed_transitions"] == ["CANCELLED", "CONFIRMED"]
    assert "cost_price" not in str(detail)


# --------------------------------------------------------------------------
# Ảnh chụp giá
# --------------------------------------------------------------------------
def test_price_change_does_not_alter_existing_order(client, staff_headers, ready_cart, db):
    cart_id, headers, sku = ready_cart
    order = do_checkout(client, cart_id, headers).json()
    client.patch(
        f"/api/admin/variants/{sku}", json={"sale_price": "999000.00"}, headers=staff_headers
    )
    after = client.get(
        f"/api/orders/{order['order_id']}", headers={"X-Order-Token": headers["X-Cart-Token"]}
    ).json()
    assert after["items"][0]["unit_price"] == "150000.00"
    assert after["grand_total"] == "300000.00"
    assert db.execute(text("SELECT unit_price FROM order_items")).scalar_one() == Decimal(
        "150000.00"
    )


def test_checked_out_cart_is_frozen(client, ready_cart):
    cart_id, headers, sku = ready_cart
    do_checkout(client, cart_id, headers)
    r = add(client, cart_id, headers, sku)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CART_NOT_ACTIVE"


# --------------------------------------------------------------------------
# Đối chứng âm cho phép đo
# --------------------------------------------------------------------------
def test_NEGATIVE_control_order_count_detects_duplicates(client, staff_headers, db):
    sku = make_sku(client, staff_headers)
    for _ in range(2):
        cart_id, headers = new_cart(client)
        add(client, cart_id, headers, sku)
        do_checkout(client, cart_id, headers)
    assert order_count(db) == 2


def test_cart_grand_total_equals_checkout_total_with_shipping_fee(client, ready_cart, monkeypatch):
    """Giỏ và checkout dùng CÙNG hàm phí ship ⇒ `expected_total` từ giỏ luôn khớp."""
    from app.config import settings

    monkeypatch.setattr(settings, "shipping_fee_flat", "30000.00")
    cart_id, headers, _ = ready_cart
    cart = client.get(f"/api/cart/{cart_id}", headers=headers).json()
    assert (cart["subtotal"], cart["shipping_fee"], cart["grand_total"]) == (
        "300000.00",
        "30000.00",
        "330000.00",
    )
    r = do_checkout(client, cart_id, headers, expected_total=cart["grand_total"])
    assert r.status_code == 201, r.text
    assert (r.json()["shipping_fee"], r.json()["grand_total"]) == ("30000.00", "330000.00")


def test_empty_cart_has_no_shipping_fee(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "shipping_fee_flat", "30000.00")
    cart_id, headers = new_cart(client)
    cart = client.get(f"/api/cart/{cart_id}", headers=headers).json()
    assert (cart["subtotal"], cart["shipping_fee"], cart["grand_total"]) == ("0.00", "0.00", "0.00")
