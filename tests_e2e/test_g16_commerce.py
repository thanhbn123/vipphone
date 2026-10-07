"""E2E trình duyệt THẬT cho G16 — sản phẩm → giỏ → checkout → đơn thành công.

Đo những điều tầng API không đo được:

1. Nút "Thêm vào giỏ" trên trang sản phẩm thật sự tạo giỏ + dòng giỏ.
2. Trang checkout gửi ĐÚNG MỘT đơn kể cả khi bấm đúp nút đặt hàng.
3. Trang `/order/success` đọc lại đơn bằng token của chủ đơn.
4. dataLayer có đủ 4 event thương mại và KHÔNG chứa PII.
5. Không lỗi console/CSP; không tràn ngang ở 320/375/390/430px.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text

from tests.conftest import TEST_DATABASE_URL
from tests_e2e.test_g14_shop import api
from tests_e2e.test_g15_reco import RECORDER, payloads

pytestmark = [pytest.mark.e2e]

NAME = "Khách DEMO-STAGING"
PHONE = "0987654321"
EMAIL = "demo-staging@example.com"
ADDRESS = "99 Đường DEMO-STAGING"


def _count(sql: str) -> int:
    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        with engine.connect() as conn:
            return conn.execute(text(sql)).scalar_one()
    finally:
        engine.dispose()


@pytest.fixture
def product(live_server):
    from tests.conftest import STAFF_KEY

    created = api(
        live_server,
        "/api/admin/products",
        method="POST",
        key=STAFF_KEY,
        body={
            "name": "Kính DEMO-STAGING",
            "slug": "demo-staging-kinh",
            "category_code": "SCREEN_PROTECTOR",
        },
    )
    api(
        live_server,
        f"/api/admin/products/{created['product_id']}/variants",
        method="POST",
        key=STAFF_KEY,
        body={"sku": "DEMO-KINH-E2E", "variant_name": "Bản demo", "sale_price": "120000.50"},
    )
    return "demo-staging-kinh"


@pytest.fixture
def shop_page(browser, console_errors):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.add_init_script(RECORDER)
    page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    try:
        yield page
    finally:
        context.close()


def _add_to_cart(page, base, slug, times=1):
    page.goto(f"{base}/product/{slug}")
    page.wait_for_selector("[data-add-sku]")
    for _ in range(times):
        page.click("[data-add-sku]")
        page.wait_for_selector("#cartStatus.ok:not([hidden])")


def _fill_checkout(page):
    page.fill("#full_name", NAME)
    page.fill("#phone", PHONE)
    page.fill("#email", EMAIL)
    page.fill("#address_line", ADDRESS)
    page.fill("#district", "Quận 1")
    page.fill("#province", "TP Hồ Chí Minh")


def test_full_purchase_flow_creates_one_order(shop_page, live_server, product, console_errors):
    page = shop_page
    _add_to_cart(page, live_server, product, times=2)

    page.goto(f"{live_server}/cart")
    page.wait_for_selector("#cartTotals:not([hidden])")
    assert page.inner_text("#cartGrand").strip() == "240.001,00 đ"
    assert page.input_value(".cart-line input[type=number]") == "2"

    page.click("#toCheckout")
    page.wait_for_url("**/checkout")
    page.wait_for_selector("#summaryLines .cart-line")
    _fill_checkout(page)
    # Bấm ĐÚP: nút bị khoá ngay + Idempotency-Key cố định ⇒ đúng một đơn.
    page.dblclick("#placeOrder")
    page.wait_for_url("**/order/success")
    page.wait_for_selector("#orderBox:not([hidden])")

    assert page.inner_text("#orderGrand").strip() == "240.001,00 đ"
    assert page.inner_text("#orderNumber").strip().startswith("VP")
    assert "0987***321" in page.inner_text("#orderRecipient")
    assert _count("SELECT count(*) FROM orders") == 1
    assert _count("SELECT count(*) FROM order_items") == 1

    events = payloads(page)
    names = [e.get("event") for e in events]
    for required in (
        "vipphone_add_to_cart",
        "vipphone_checkout_start",
        "vipphone_order_created",
    ):
        assert required in names, names
    commerce_events = [e for e in events if e.get("event", "").startswith("vipphone_")]
    blob = json.dumps(commerce_events, ensure_ascii=False)
    for value in (NAME, PHONE, EMAIL, ADDRESS, "0987***321"):
        assert value not in blob, value
    keys = {k for e in commerce_events for k in e}
    assert not keys & {"phone", "email", "full_name", "address", "address_line", "recipient_name"}
    assert console_errors == []


def test_remove_from_cart_event_and_empty_state(shop_page, live_server, product, console_errors):
    page = shop_page
    _add_to_cart(page, live_server, product)
    page.goto(f"{live_server}/cart")
    page.wait_for_selector(".cart-line")
    page.click(".cart-line .secondary-btn")
    page.wait_for_selector("#cartEmpty:not([hidden])")
    assert page.is_hidden("#toCheckout")
    assert "vipphone_remove_from_cart" in [e.get("event") for e in payloads(page)]
    assert console_errors == []


@pytest.mark.parametrize("width", [320, 375, 390, 430])
def test_commerce_pages_do_not_overflow_on_mobile(browser, live_server, product, width):
    context = browser.new_context(viewport={"width": width, "height": 800})
    page = context.new_page()
    try:
        _add_to_cart(page, live_server, product)
        for path, ready in (
            (f"/product/{product}", "[data-add-sku]"),
            ("/cart", ".cart-line"),
            ("/checkout", "#summaryLines .cart-line"),
        ):
            page.goto(f"{live_server}{path}")
            page.wait_for_selector(ready)
            overflow = page.evaluate(
                "document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            assert overflow == 0, (path, width, overflow)
    finally:
        context.close()
