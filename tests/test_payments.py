"""G17 — Nền tảng thanh toán. Thiết kế: `docs/payments.md`.

Bắt buộc của gate: COD không tự PAID · chuyển khoản chờ nhân viên · webhook giả lập
chứng minh: chữ ký, chống trùng, idempotent, số tiền, tiền tệ, khớp đơn/khoản thu,
kiểm chuyển trạng thái · `orders.payment_status` chỉ đổi qua tầng dịch vụ.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest
from sqlalchemy import text

from app.payments.providers import mock_signature
from tests.test_commerce import add, checkout_body, key, make_sku, new_cart

pytestmark = pytest.mark.integration

SECRET = "mock-webhook-secret-for-tests-only"
WEBHOOK = "/api/payments/webhooks/staging-mock"


def place_order(client, staff_headers, method="COD", sku="KINH-01", price="150000.00"):
    if not client.get("/api/admin/products", headers=staff_headers).json()["items"]:
        make_sku(client, staff_headers, sku=sku, price=price)
    cart_id, headers = new_cart(client)
    assert add(client, cart_id, headers, sku, 2).status_code == 200
    body = checkout_body(cart_id, payment_method=method)
    r = client.post("/api/checkout", json=body, headers={**headers, "Idempotency-Key": key()})
    assert r.status_code == 201, r.text
    return r.json(), headers


def admin_payments(client, staff_headers, order_id):
    r = client.get(f"/api/admin/orders/{order_id}/payments", headers=staff_headers)
    assert r.status_code == 200, r.text
    return r.json()


def set_status(client, staff_headers, order_id, *statuses):
    for status in statuses:
        r = client.post(
            f"/api/admin/orders/{order_id}/status",
            json={"to_status": status},
            headers=staff_headers,
        )
        assert r.status_code == 200, r.text


def act(client, staff_headers, payment_id, action, note=None):
    return client.post(
        f"/api/admin/payments/{payment_id}/{action}", json={"note": note}, headers=staff_headers
    )


def signed(body: dict, *, secret=SECRET, ts=None, tamper=False):
    raw = json.dumps(body).encode()
    timestamp = str(int(time.time()) if ts is None else ts)
    sig = mock_signature(secret, timestamp, raw)
    if tamper:
        raw = raw.replace(b"PAID", b"FAIL")
    return raw, {
        "X-Mock-Signature": sig,
        "X-Mock-Timestamp": timestamp,
        "Content-Type": "application/json",
    }


def mock_event(order, **overrides):
    payment = order["payment"]
    body = {
        "event_id": f"evt_{uuid.uuid4().hex}",
        "payment_reference": payment["provider_reference"],
        "status": "PAID",
        "amount": payment["amount"],
        "currency": payment["currency"],
    }
    body.update(overrides)
    return body


def send(client, body, **kw):
    raw, headers = signed(body, **kw)
    return client.post(WEBHOOK, content=raw, headers=headers)


def order_payment_status(db) -> list[str]:
    return db.execute(text("SELECT payment_status FROM orders ORDER BY id")).scalars().all()


# --------------------------------------------------------------------------
# COD
# --------------------------------------------------------------------------
def test_cod_starts_pending_and_never_auto_paid(client, staff_headers, db):
    order, _ = place_order(client, staff_headers, "COD")
    assert order["payment"]["method"] == "COD"
    assert order["payment"]["status"] == "PENDING"
    assert order["payment_status"] == "PENDING"
    # Đi hết vòng giao hàng mà KHÔNG xác nhận thu tiền ⇒ vẫn PENDING.
    set_status(
        client, staff_headers, order["order_id"], "CONFIRMED", "PROCESSING", "SHIPPED", "COMPLETED"
    )
    assert order_payment_status(db) == ["PENDING"]
    assert admin_payments(client, staff_headers, order["order_id"])[0]["status"] == "PENDING"


def test_cod_confirm_requires_shipped(client, staff_headers, db):
    order, _ = place_order(client, staff_headers, "COD")
    pid = admin_payments(client, staff_headers, order["order_id"])[0]["payment_id"]
    r = act(client, staff_headers, pid, "confirm")
    assert r.status_code == 409 and r.json()["error"]["code"] == "COD_NOT_DELIVERED"
    set_status(client, staff_headers, order["order_id"], "CONFIRMED", "PROCESSING", "SHIPPED")
    r = act(client, staff_headers, pid, "confirm", "Đã thu tiền shipper")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PAID" and r.json()["confirmed_by"].startswith("staff:")
    assert order_payment_status(db) == ["PAID"]


def test_cod_webhook_is_rejected(client, staff_headers):
    order, _ = place_order(client, staff_headers, "COD")
    r = send(
        client,
        {
            "event_id": "e1",
            "payment_reference": "X",
            "status": "PAID",
            "amount": "1",
            "currency": "VND",
        },
    )
    assert r.status_code == 404
    assert order["payment"]["status"] == "PENDING"


# --------------------------------------------------------------------------
# Chuyển khoản thủ công
# --------------------------------------------------------------------------
def test_bank_transfer_pending_until_staff_confirms(client, staff_headers, db):
    order, headers = place_order(client, staff_headers, "BANK_TRANSFER_MANUAL")
    assert order["payment"]["status"] == "PENDING"
    assert order["payment"]["instructions"].startswith(
        f"Ghi nội dung chuyển khoản: {order['order_number']}."
    )
    pid = admin_payments(client, staff_headers, order["order_id"])[0]["payment_id"]
    r = act(client, staff_headers, pid, "confirm", "Khớp sao kê")
    assert r.status_code == 200 and r.json()["status"] == "PAID"
    view = client.get(
        f"/api/orders/{order['order_id']}", headers={"X-Order-Token": headers["X-Cart-Token"]}
    ).json()
    assert (view["payment_status"], view["payment"]["status"]) == ("PAID", "PAID")
    # Xác nhận lần hai ⇒ 409, không đổi gì.
    assert act(client, staff_headers, pid, "confirm").status_code == 409


def test_staff_fail_then_no_more_changes(client, staff_headers, db):
    order, _ = place_order(client, staff_headers, "BANK_TRANSFER_MANUAL")
    pid = admin_payments(client, staff_headers, order["order_id"])[0]["payment_id"]
    assert act(client, staff_headers, pid, "fail", "Không thấy tiền").json()["status"] == "FAILED"
    assert order_payment_status(db) == ["FAILED"]
    assert act(client, staff_headers, pid, "confirm").status_code == 409


def test_cancel_order_cancels_pending_payment(client, staff_headers, db):
    order, _ = place_order(client, staff_headers, "BANK_TRANSFER_MANUAL")
    set_status(client, staff_headers, order["order_id"], "CANCELLED")
    payment = admin_payments(client, staff_headers, order["order_id"])[0]
    assert payment["status"] == "CANCELLED"
    assert order_payment_status(db) == ["UNPAID"]


def test_refund_only_for_cancelled_paid_order(client, staff_headers, db):
    order, _ = place_order(client, staff_headers, "BANK_TRANSFER_MANUAL")
    pid = admin_payments(client, staff_headers, order["order_id"])[0]["payment_id"]
    act(client, staff_headers, pid, "confirm")
    r = act(client, staff_headers, pid, "refund")
    assert r.status_code == 409 and r.json()["error"]["code"] == "REFUND_REQUIRES_CANCELLED_ORDER"
    set_status(client, staff_headers, order["order_id"], "CANCELLED")
    # Đơn đã PAID bị huỷ: khoản thu GIỮ PAID cho tới khi hoàn tiền.
    assert admin_payments(client, staff_headers, order["order_id"])[0]["status"] == "PAID"
    assert act(client, staff_headers, pid, "refund").json()["status"] == "REFUNDED"
    assert order_payment_status(db) == ["REFUNDED"]


def test_one_open_payment_per_order_enforced_by_db(client, staff_headers, db):
    from sqlalchemy.exc import IntegrityError

    place_order(client, staff_headers, "COD")
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO payments (payment_id, order_id, method, status, amount, currency) "
                "SELECT gen_random_uuid(), id, 'COD', 'PENDING', grand_total, currency FROM orders"
            )
        )
        db.flush()
    db.rollback()


# --------------------------------------------------------------------------
# STAGING_MOCK webhook
# --------------------------------------------------------------------------
@pytest.fixture
def mock_order(client, staff_headers):
    order, headers = place_order(client, staff_headers, "STAGING_MOCK")
    assert order["payment"]["provider_reference"].startswith("MOCK-")
    return order, headers


def events(db, outcome=None) -> int:
    sql = "SELECT count(*) FROM payment_events WHERE provider = 'staging-mock'"
    if outcome:
        sql += f" AND outcome = '{outcome}'"
    return db.execute(text(sql)).scalar_one()


def test_valid_signed_webhook_marks_paid_and_syncs_order(client, mock_order, db):
    order, headers = mock_order
    r = send(client, mock_event(order))
    assert (r.status_code, r.json()) == (200, {"outcome": "APPLIED", "reason": None})
    view = client.get(
        f"/api/orders/{order['order_id']}", headers={"X-Order-Token": headers["X-Cart-Token"]}
    ).json()
    assert (view["payment_status"], view["payment"]["status"]) == ("PAID", "PAID")
    assert events(db, "APPLIED") == 1


def test_bad_signature_rejected_and_nothing_written(client, mock_order, db):
    order, _ = mock_order
    for kw in ({"secret": "khoa-sai"}, {"tamper": True}):
        r = send(client, mock_event(order), **kw)
        assert r.status_code == 401
    raw = json.dumps(mock_event(order)).encode()
    assert client.post(WEBHOOK, content=raw).status_code == 401
    assert events(db) == 0
    assert order_payment_status(db) == ["PENDING"]


def test_stale_timestamp_rejected(client, mock_order, db):
    order, _ = mock_order
    r = send(client, mock_event(order), ts=int(time.time()) - 3600)
    assert r.status_code == 401
    assert order_payment_status(db) == ["PENDING"]


def test_duplicate_event_is_deduped_and_idempotent(client, mock_order, db):
    order, _ = mock_order
    body = mock_event(order)
    first = send(client, body)
    second = send(client, body)
    assert first.json()["outcome"] == "APPLIED"
    assert (second.status_code, second.json()["outcome"]) == (200, "DUPLICATE")
    assert events(db) == 1
    status_events = db.execute(
        text("SELECT count(*) FROM order_status_events WHERE to_value = 'PAID'")
    ).scalar_one()
    assert status_events == 1


def test_second_paid_event_with_new_id_is_invalid_transition(client, mock_order, db):
    order, _ = mock_order
    send(client, mock_event(order))
    r = send(client, mock_event(order))
    assert (r.status_code, r.json()["reason"]) == (409, "INVALID_TRANSITION")
    assert order_payment_status(db) == ["PAID"]


@pytest.mark.parametrize(
    "override, reason",
    [
        ({"amount": "1.00"}, "AMOUNT_MISMATCH"),
        ({"amount": "300000.01"}, "AMOUNT_MISMATCH"),
        ({"currency": "USD"}, "CURRENCY_MISMATCH"),
        ({"payment_reference": "MOCK-KHONGCO"}, "PAYMENT_NOT_FOUND"),
        ({"status": "REFUNDED"}, "UNKNOWN_STATUS"),
    ],
)
def test_mismatched_webhook_rejected_and_recorded(client, mock_order, db, override, reason):
    order, _ = mock_order
    r = send(client, mock_event(order, **override))
    assert r.json() == {"outcome": "REJECTED", "reason": reason}
    assert r.status_code in (404, 409, 422)
    assert order_payment_status(db) == ["PENDING"]
    assert events(db, "REJECTED") == 1


def test_webhook_for_other_orders_payment_cannot_cross(client, staff_headers, db):
    """Khoản thu khớp theo MÃ THAM CHIẾU riêng của nó — webhook đơn A không chạm đơn B."""
    a, _ = place_order(client, staff_headers, "STAGING_MOCK")
    b, _ = place_order(client, staff_headers, "STAGING_MOCK")
    send(client, mock_event(a))
    assert order_payment_status(db) == ["PAID", "PENDING"]
    assert b["payment"]["provider_reference"] != a["payment"]["provider_reference"]


def test_failed_webhook_marks_failed(client, mock_order, db):
    order, _ = mock_order
    assert send(client, mock_event(order, status="FAILED")).json()["outcome"] == "APPLIED"
    assert order_payment_status(db) == ["FAILED"]


def test_malformed_payload_rejected(client, mock_order, db):
    raw = b'{"event_id": "x"}'
    ts = str(int(time.time()))
    r = client.post(
        WEBHOOK,
        content=raw,
        headers={"X-Mock-Signature": mock_signature(SECRET, ts, raw), "X-Mock-Timestamp": ts},
    )
    assert (r.status_code, r.json()["reason"]) == (400, "MALFORMED_PAYLOAD")


def test_staff_cannot_hand_confirm_mock_payment(client, staff_headers, mock_order):
    order, _ = mock_order
    pid = admin_payments(client, staff_headers, order["order_id"])[0]["payment_id"]
    r = act(client, staff_headers, pid, "confirm")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFIRM_NOT_ALLOWED"


def test_mock_disabled_in_production(monkeypatch, client, staff_headers, db):
    from app.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    assert settings.payment_mock_enabled is False
    make_sku(client, staff_headers)
    cart_id, headers = new_cart(client)
    add(client, cart_id, headers, "KINH-01")
    r = client.post(
        "/api/checkout",
        json=checkout_body(cart_id, payment_method="STAGING_MOCK"),
        headers={**headers, "Idempotency-Key": key()},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "PAYMENT_METHOD_UNAVAILABLE"
    # Hook thanh toán ném lỗi ⇒ CẢ ĐƠN rollback, không có đơn "nửa vời".
    assert db.execute(text("SELECT count(*) FROM orders")).scalar_one() == 0


def test_mock_disabled_without_secret(monkeypatch, client, mock_order, db):
    from app.config import settings

    order, _ = mock_order
    monkeypatch.setattr(settings, "payment_mock_webhook_secret", "")
    assert send(client, mock_event(order)).status_code == 401


def test_unknown_payment_method_rejected(client, staff_headers):
    make_sku(client, staff_headers)
    cart_id, headers = new_cart(client)
    add(client, cart_id, headers, "KINH-01")
    r = client.post(
        "/api/checkout",
        json=checkout_body(cart_id, payment_method="CREDIT_CARD"),
        headers={**headers, "Idempotency-Key": key()},
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------
# Không dữ liệu nhạy cảm + quyền
# --------------------------------------------------------------------------
def test_payment_events_store_no_raw_payload_or_signature(client, mock_order, db):
    order, _ = mock_order
    body = mock_event(order)
    raw, headers = signed(body)
    client.post(WEBHOOK, content=raw, headers=headers)
    columns = {
        r[0]
        for r in db.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='payment_events'"
            )
        )
    }
    assert not columns & {"payload", "raw_payload", "signature", "headers", "card_number"}
    dump = json.dumps(
        [list(map(str, r)) for r in db.execute(text("SELECT * FROM payment_events")).all()]
    )
    assert headers["X-Mock-Signature"] not in dump


def test_admin_payment_routes_require_staff(client, mock_order):
    order, headers = mock_order
    assert client.get("/api/admin/payments").status_code == 401
    assert client.get(f"/api/admin/orders/{order['order_id']}/payments").status_code == 401
    r = client.post(f"/api/admin/payments/{uuid.uuid4()}/confirm", json={}, headers=headers)
    assert r.status_code == 401


def test_admin_payment_list_filters(client, staff_headers):
    place_order(client, staff_headers, "COD")
    place_order(client, staff_headers, "BANK_TRANSFER_MANUAL")
    page = client.get("/api/admin/payments", headers=staff_headers).json()
    assert page["total"] == 2
    only = client.get("/api/admin/payments", params={"method": "COD"}, headers=staff_headers).json()
    assert [p["method"] for p in only["items"]] == ["COD"]


def test_payment_amount_equals_order_total(client, staff_headers, db):
    place_order(client, staff_headers, "COD")
    row = db.execute(
        text("SELECT p.amount = o.grand_total FROM payments p JOIN orders o ON o.id = p.order_id")
    ).scalar_one()
    assert row is True


def test_order_payment_status_only_via_service(client, staff_headers, db):
    """Mọi lần đổi `orders.payment_status` đều có một dòng vết tương ứng."""
    order, _ = place_order(client, staff_headers, "BANK_TRANSFER_MANUAL")
    pid = admin_payments(client, staff_headers, order["order_id"])[0]["payment_id"]
    act(client, staff_headers, pid, "confirm")
    trail = db.execute(
        text(
            "SELECT from_value, to_value FROM order_status_events "
            "WHERE field = 'payment_status' ORDER BY id"
        )
    ).all()
    assert [tuple(r) for r in trail] == [("UNPAID", "PENDING"), ("PENDING", "PAID")]
