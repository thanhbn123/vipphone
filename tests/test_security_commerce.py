"""Rà soát bảo mật cho bề mặt thương mại mới — đo bằng runtime, không chỉ đọc mã.

- Rate limit riêng cho tạo giỏ / checkout (429 + Retry-After).
- CORS: origin lạ KHÔNG được cấp quyền gọi checkout/giỏ (không có ACAO).
- Không cookie ⇒ không có bề mặt CSRF: response thương mại không đặt Set-Cookie.
- Header bảo mật có trên trang thương mại mới; CSP không nới.
"""

from __future__ import annotations

import pytest

from app import security
from tests.test_commerce import add, checkout_body, key, make_sku, new_cart

pytestmark = pytest.mark.integration


def test_cart_creation_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(security.commerce_rate_limiter, "limit", 2)
    security.commerce_rate_limiter.reset()
    try:
        assert client.post("/api/cart").status_code == 201
        assert client.post("/api/cart").status_code == 201
        blocked = client.post("/api/cart")
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) >= 1
    finally:
        security.commerce_rate_limiter.reset()


def test_checkout_is_rate_limited(client, staff_headers, monkeypatch, db):
    from sqlalchemy import text

    make_sku(client, staff_headers)
    cart_id, headers = new_cart(client)
    add(client, cart_id, headers, "KINH-01")
    monkeypatch.setattr(security.commerce_rate_limiter, "limit", 1)
    security.commerce_rate_limiter.reset()
    try:
        bad = {**checkout_body(cart_id), "shipping": {}}
        assert (
            client.post(
                "/api/checkout", json=bad, headers={**headers, "Idempotency-Key": key()}
            ).status_code
            == 422
        )
        r = client.post(
            "/api/checkout",
            json=checkout_body(cart_id),
            headers={**headers, "Idempotency-Key": key()},
        )
        assert r.status_code == 429
        assert db.execute(text("SELECT count(*) FROM orders")).scalar_one() == 0
    finally:
        security.commerce_rate_limiter.reset()


@pytest.mark.parametrize(
    "path", ["/api/checkout", "/api/cart", "/api/payments/webhooks/staging-mock"]
)
def test_foreign_origin_gets_no_cors_grant(client, path):
    r = client.options(
        path,
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-cart-token,idempotency-key,content-type",
        },
    )
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_commerce_responses_set_no_cookies(client, staff_headers):
    make_sku(client, staff_headers)
    created = client.post("/api/cart")
    cart_id, token = created.json()["cart_id"], created.json()["cart_token"]
    headers = {"X-Cart-Token": token}
    responses = [
        created,
        add(client, cart_id, headers, "KINH-01"),
        client.post(
            "/api/checkout",
            json=checkout_body(cart_id),
            headers={**headers, "Idempotency-Key": key()},
        ),
    ]
    for r in responses:
        assert "set-cookie" not in {k.lower() for k in r.headers}


@pytest.mark.parametrize(
    "path", ["/cart", "/checkout", "/order/success", "/admin-commerce.html", "/shop"]
)
def test_commerce_pages_have_strict_headers(client, path):
    r = client.get(path)
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
