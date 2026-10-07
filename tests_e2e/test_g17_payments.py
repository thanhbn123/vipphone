"""E2E trình duyệt THẬT cho G17 — chọn phương thức + trạng thái thanh toán.

1. `/checkout` hiện ĐÚNG các phương thức máy chủ cho phép (từ `/api/public-config`).
2. Chuyển khoản: trang đơn hiện "đang chờ" + hướng dẫn mã đơn; event `payment_pending`.
3. Cổng giả lập: webhook ĐÃ KÝ ⇒ tải lại trang đơn thấy "đã nhận tiền";
   event `payment_succeeded`. Không event nào chứa PII hay dữ liệu tài khoản.
"""

from __future__ import annotations

import json
import time
import urllib.request
import uuid

import pytest

from app.payments.providers import mock_signature
from tests_e2e import test_g16_commerce as g16
from tests_e2e.test_g15_reco import payloads
from tests_e2e.test_g16_commerce import _add_to_cart, _fill_checkout

pytestmark = [pytest.mark.e2e]

#: Dùng lại fixture của bộ G16 (cùng sản phẩm demo, cùng bộ ghi dataLayer).
product = g16.product
shop_page = g16.shop_page

SECRET = "mock-webhook-secret-for-tests-only"


def _checkout(page, base, slug, method):
    _add_to_cart(page, base, slug)
    page.goto(f"{base}/checkout")
    page.wait_for_selector(f"#pay_{method}")
    _fill_checkout(page)
    page.check(f"#pay_{method}")
    page.click("#placeOrder")
    page.wait_for_url("**/order/success")
    page.wait_for_selector("#paymentBox:not([hidden])")


def test_methods_offered_match_server_config(shop_page, live_server, product):
    _add_to_cart(shop_page, live_server, product)
    shop_page.goto(f"{live_server}/checkout")
    shop_page.wait_for_selector("#pay_COD")
    offered = shop_page.eval_on_selector_all(
        "input[name=payment_method]", "els => els.map(e => e.value)"
    )
    with urllib.request.urlopen(live_server + "/api/public-config") as r:
        assert offered == json.loads(r.read())["payment_methods"]
    assert offered[0] == "COD"


def test_bank_transfer_shows_pending_with_reference(
    shop_page, live_server, product, console_errors
):
    _checkout(shop_page, live_server, product, "BANK_TRANSFER_MANUAL")
    number = shop_page.inner_text("#orderNumber").strip()
    assert shop_page.inner_text("#paymentTitle").strip() == "Thanh toán: đang chờ"
    assert shop_page.inner_text("#paymentText").startswith(f"Ghi nội dung chuyển khoản: {number}.")
    names = [e.get("event") for e in payloads(shop_page)]
    assert "vipphone_payment_method_selected" in names
    assert "vipphone_payment_pending" in names
    assert console_errors == []


def test_mock_gateway_webhook_marks_paid(shop_page, live_server, product, console_errors):
    _checkout(shop_page, live_server, product, "STAGING_MOCK")
    stored = json.loads(shop_page.evaluate("sessionStorage.getItem('vipphone_last_order_v1')"))
    request = urllib.request.Request(
        f"{live_server}/api/orders/{stored['order_id']}", headers={"X-Order-Token": stored["token"]}
    )
    with urllib.request.urlopen(request) as r:
        order = json.loads(r.read())
    body = json.dumps(
        {
            "event_id": f"evt_{uuid.uuid4().hex}",
            "payment_reference": order["payment"]["provider_reference"],
            "status": "PAID",
            "amount": order["payment"]["amount"],
            "currency": order["payment"]["currency"],
        }
    ).encode()
    ts = str(int(time.time()))
    hook = urllib.request.Request(
        f"{live_server}/api/payments/webhooks/staging-mock",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Mock-Timestamp": ts,
            "X-Mock-Signature": mock_signature(SECRET, ts, body),
        },
    )
    with urllib.request.urlopen(hook) as r:
        assert json.loads(r.read())["outcome"] == "APPLIED"

    shop_page.reload()
    shop_page.wait_for_selector("#paymentBox.ok:not([hidden])")
    assert shop_page.inner_text("#paymentTitle").strip() == "Thanh toán: đã nhận tiền"

    events = [
        e for e in payloads(shop_page) if str(e.get("event", "")).startswith("vipphone_payment")
    ]
    assert "vipphone_payment_succeeded" in [e["event"] for e in events]
    keys = {k for e in events for k in e}
    assert keys <= {"event", "order_number", "payment_method", "value", "currency"}, keys
    assert console_errors == []
