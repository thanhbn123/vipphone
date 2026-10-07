"""Attribution. Thiết kế: `docs/attribution.md`.

Trả lời được 3 câu hỏi, không PII:
- nguồn nào TẠO RA khách (first-touch)        → model=first_touch
- chiến dịch nào RA ĐƠN (last-touch lúc đặt)   → model=order, dimension=utm_campaign
- referrer nào RA DOANH THU                    → model=order, dimension=ref
First-touch KHÔNG bị ghi đè.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.test_commerce import add, checkout_body, key, make_sku, new_cart

pytestmark = pytest.mark.integration


def lead(client, phone, **attribution):
    body = {
        "full_name": "Khách",
        "phone": phone,
        "iphone_model": "iphone-16-pro-max",
        "consent": True,
        **attribution,
    }
    r = client.post("/api/leads", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def order(client, phone, attribution=None, quantity=1):
    cart_id, headers = new_cart(client)
    add(client, cart_id, headers, "KINH-01", quantity)
    body = checkout_body(cart_id, attribution=attribution)
    body["customer"]["phone"] = phone
    body["shipping"]["phone"] = phone
    r = client.post("/api/checkout", json=body, headers={**headers, "Idempotency-Key": key()})
    assert r.status_code == 201, r.text
    return r.json()


def report(client, staff_headers, **params):
    r = client.get("/api/admin/reports/attribution", params=params, headers=staff_headers)
    assert r.status_code == 200, r.text
    return [
        (row["key"], row["customers"], row["orders"], row["revenue"]) for row in r.json()["rows"]
    ]


@pytest.fixture(autouse=True)
def sku(client, staff_headers):
    make_sku(client, staff_headers, price="100000.00")


def test_lead_first_touch_preserved_when_later_order_has_other_source(client, staff_headers, db):
    lead(client, "0911111111", source="bni", campaign="thang10", utm_campaign="qua-op", ref="BNI-A")
    placed = order(
        client, "0911111111", {"source": "zalo", "utm_campaign": "flash-sale", "ref": "KOL-B"}
    )
    acq = db.execute(
        text("SELECT source, campaign, utm_campaign, ref, acquired_via FROM customer_acquisition")
    ).one()
    assert tuple(acq) == ("bni", "thang10", "qua-op", "BNI-A", "LEAD")
    o = db.execute(text("SELECT source, utm_campaign, ref FROM orders")).one()
    assert tuple(o) == ("zalo", "flash-sale", "KOL-B")

    detail = client.get(f"/api/admin/orders/{placed['order_id']}", headers=staff_headers).json()
    assert detail["attribution"]["utm_campaign"] == "flash-sale"
    assert detail["customer_first_touch"]["utm_campaign"] == "qua-op"


def test_direct_shop_customer_gets_first_touch_from_first_order_only(client, db):
    first = order(client, "0922222222", {"source": "facebook", "utm_campaign": "ra-mat"})
    order(client, "0922222222", {"source": "google", "utm_campaign": "tim-kiem"})
    acq = db.execute(
        text("SELECT source, utm_campaign, acquired_via, first_order_id FROM customer_acquisition")
    ).one()
    first_pk = db.execute(
        text("SELECT id FROM orders WHERE order_number = :n"), {"n": first["order_number"]}
    ).scalar_one()
    assert tuple(acq) == ("facebook", "ra-mat", "ORDER", first_pk)


def test_later_lead_does_not_overwrite_order_first_touch(client, db):
    order(client, "0933333333", {"source": "tiktok"})
    lead(client, "0933333333", source="bni")
    assert db.execute(text("SELECT source, acquired_via FROM customer_acquisition")).one() == (
        "tiktok",
        "ORDER",
    )


def test_order_without_attribution_is_direct(client, db):
    order(client, "0944444444")
    assert db.execute(text("SELECT source, ref FROM orders")).one() == (None, None)


@pytest.mark.parametrize(
    "bad",
    [
        {"source": "<script>"},
        {"ref": "có dấu"},
        {"utm_campaign": "x" * 65},
        {"phone": "0912345678"},
    ],
)
def test_attribution_is_whitelisted(client, bad, db):
    cart_id, headers = new_cart(client)
    add(client, cart_id, headers, "KINH-01")
    r = client.post(
        "/api/checkout",
        json=checkout_body(cart_id, attribution=bad),
        headers={**headers, "Idempotency-Key": key()},
    )
    assert r.status_code == 422
    assert db.execute(text("SELECT count(*) FROM orders")).scalar_one() == 0


def test_reports_answer_the_three_questions(client, staff_headers):
    # Khách 1: đến từ BNI (lead), mua 2 đơn qua chiến dịch flash-sale, referrer KOL-B.
    lead(client, "0911111111", source="bni", utm_campaign="qua-op", ref="BNI-A")
    order(client, "0911111111", {"source": "zalo", "utm_campaign": "flash-sale", "ref": "KOL-B"}, 2)
    order(client, "0911111111", {"source": "zalo", "utm_campaign": "flash-sale", "ref": "KOL-B"})
    # Khách 2: đến thẳng cửa hàng từ facebook.
    order(client, "0922222222", {"source": "facebook", "utm_campaign": "ra-mat", "ref": "KOL-C"})
    # Khách 3: chỉ để lại lead, chưa mua.
    lead(client, "0955555555", source="bni")

    # 1) Nguồn nào TẠO RA khách (first-touch).
    assert report(client, staff_headers, model="first_touch", dimension="source") == [
        ("bni", 2, 2, "300000.00"),
        ("facebook", 1, 1, "100000.00"),
    ]
    # 2) Chiến dịch nào RA ĐƠN (last-touch lúc đặt).
    assert report(client, staff_headers, model="order", dimension="utm_campaign") == [
        ("flash-sale", 1, 2, "300000.00"),
        ("ra-mat", 1, 1, "100000.00"),
    ]
    # 3) Referrer nào RA DOANH THU.
    assert report(client, staff_headers, model="order", dimension="ref") == [
        ("KOL-B", 1, 2, "300000.00"),
        ("KOL-C", 1, 1, "100000.00"),
    ]


def test_cancelled_orders_excluded_from_revenue(client, staff_headers):
    placed = order(client, "0911111111", {"ref": "KOL-B"})
    client.post(
        f"/api/admin/orders/{placed['order_id']}/status",
        json={"to_status": "CANCELLED"},
        headers=staff_headers,
    )
    assert report(client, staff_headers, model="order", dimension="ref") == [
        ("KOL-B", 1, 0, "0.00")
    ]


def test_report_has_no_pii_and_requires_staff(client, staff_headers):
    lead(client, "0911111111", source="bni")
    order(client, "0911111111", {"source": "bni"})
    assert client.get("/api/admin/reports/attribution").status_code == 401
    body = client.get("/api/admin/reports/attribution", headers=staff_headers).text
    for pii in ("0911111111", "Khách", "full_name", "phone", "email", "address"):
        assert pii not in body


def test_report_rejects_unknown_dimension(client, staff_headers):
    r = client.get(
        "/api/admin/reports/attribution",
        params={"dimension": "phone"},
        headers=staff_headers,
    )
    assert r.status_code == 422


def test_customer_360_lists_orders_without_address(client, staff_headers):
    lead(client, "0911111111", source="bni")
    placed = order(client, "0911111111", {"source": "zalo"})
    customers = client.get(
        "/api/admin/customers", params={"phone": "0911111111"}, headers=staff_headers
    ).json()
    detail = client.get(
        f"/api/admin/customers/{customers[0]['customer_id']}", headers=staff_headers
    ).json()
    assert [(o["order_number"], o["source"], o["grand_total"]) for o in detail["orders"]] == [
        (placed["order_number"], "zalo", "100000.00")
    ]
    assert detail["acquisition"]["source"] == "bni"
    assert detail["acquisition"]["acquired_via"] == "LEAD"
    assert "address_line" not in str(detail["orders"])
