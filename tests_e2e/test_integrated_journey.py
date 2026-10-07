"""HÀNH TRÌNH TÍCH HỢP 20 BƯỚC — trình duyệt thật, API thật, PostgreSQL thật.

Khách đi từ link QR có nguồn → nhận quà → được gợi ý → mua 2 đơn (COD + chuyển
khoản) → nhân viên xác nhận thu tiền trên trang admin → kiểm kho, ảnh chụp giá,
attribution → quà vẫn phát được. Dữ liệu tổng hợp, có marker `staging-test`.

Mỗi bước có khẳng định GIÁ TRỊ ĐẦY ĐỦ, không khẳng định chuỗi con lỏng lẻo.
"""

from __future__ import annotations

import json
import urllib.request

import pytest
from sqlalchemy import create_engine, text

from tests.conftest import STAFF_KEY, TEST_DATABASE_URL
from tests_e2e.test_funnel import fill_lead_form, open_landing, submit_and_wait
from tests_e2e.test_g14_shop import api
from tests_e2e.test_g15_reco import RECORDER, payloads
from tests_e2e.test_g16_commerce import _fill_checkout

pytestmark = [pytest.mark.e2e]

PHONE = "0900000123"  # tiền tố SĐT test
DEVICE = "iphone-16-pro-max"
QUERY = "?src=staging-test&utm_campaign=staging-acceptance&ref=KOL-JOURNEY"


def q(sql: str, **params):
    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        with engine.connect() as conn:
            return conn.execute(text(sql), params).all()
    finally:
        engine.dispose()


def staff(base, path, method="GET", body=None):
    return api(base, path, method=method, key=STAFF_KEY, body=body)


@pytest.fixture
def catalog(live_server):
    def make(slug, name, category, sku, price, tracked):
        product = staff(
            live_server,
            "/api/admin/products",
            "POST",
            {"name": name, "slug": slug, "category_code": category},
        )
        staff(
            live_server,
            f"/api/admin/products/{product['product_id']}/variants",
            "POST",
            {
                "sku": sku,
                "variant_name": "Bản demo",
                "sale_price": price,
                "stock_tracking": tracked,
            },
        )
        staff(
            live_server,
            f"/api/admin/variants/{sku}/compatibility",
            "POST",
            {"device_model_code": DEVICE, "compatibility_type": "FULL"},
        )

    make(
        "demo-staging-kinh-j",
        "Kính cường lực DEMO",
        "SCREEN_PROTECTOR",
        "DEMO-KINH-J",
        "120000.00",
        True,
    )
    make("demo-staging-sac-j", "Củ sạc DEMO", "CHARGER", "DEMO-SAC-J", "250000.00", False)
    staff(
        live_server,
        "/api/admin/inventory/DEMO-KINH-J/movements",
        "POST",
        {"movement_type": "OPENING", "quantity": 5},
    )


@pytest.fixture
def journey_page(browser, console_errors):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.add_init_script(RECORDER)
    page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    try:
        yield page
    finally:
        context.close()


def _place_order(page, base, method):
    page.goto(f"{base}/checkout")
    page.wait_for_selector(f"#pay_{method}")
    _fill_checkout(page)
    page.fill("#phone", PHONE)
    page.check(f"#pay_{method}")
    page.click("#placeOrder")
    page.wait_for_url("**/order/success")
    page.wait_for_selector("#paymentBox:not([hidden])")
    return json.loads(page.evaluate("sessionStorage.getItem('vipphone_last_order_v1')"))


def test_full_customer_and_staff_journey(journey_page, live_server, catalog, console_errors):
    page, base = journey_page, live_server

    # 1. Lead từ link có nguồn.
    open_landing(page, base, QUERY)
    fill_lead_form(page, name="Khách Hành Trình", phone=PHONE, model=DEVICE)
    gift_code = submit_and_wait(page)

    # 2. Khách được tạo (hoặc dùng lại) theo SĐT chuẩn hoá.
    customer = q("SELECT id FROM customers WHERE phone_normalized = :p", p=PHONE)
    assert len(customer) == 1
    customer_pk = customer[0][0]
    # 3. Máy được nhận diện đúng MÃ.
    assert q(
        "SELECT model_code, is_primary FROM customer_devices WHERE customer_id = :c", c=customer_pk
    ) == [(DEVICE, True)]
    # 4. Trang quà hiển thị đúng mã.
    assert page.inner_text("#giftCode").strip() == gift_code

    # 5. Gợi ý hiện, đúng thứ tự, không có ốp.
    page.wait_for_selector("#recoSection:not([hidden])")
    assert page.locator("#recoList .product-name").all_inner_texts() == [
        "Kính cường lực DEMO",
        "Củ sạc DEMO",
    ]

    # 6. Bấm gợi ý → trang chi tiết.
    page.click("#recoList .reco-item[data-reco-rank='1'] .product-name a")
    page.wait_for_url("**/product/demo-staging-kinh-j")
    page.wait_for_selector("[data-add-sku]")

    # 7. Thêm vào giỏ.
    page.click("[data-add-sku='DEMO-KINH-J']")
    page.wait_for_selector("#cartStatus.ok:not([hidden])")

    # 8-10. Checkout COD ⇒ đơn tạo, thanh toán ĐANG CHỜ.
    first = _place_order(page, base, "COD")
    assert page.inner_text("#paymentTitle").strip() == "Thanh toán: đang chờ"
    cod = q(
        "SELECT o.order_number, o.status, o.payment_status, p.method, p.status, o.grand_total::text "
        "FROM orders o JOIN payments p ON p.order_id = o.id WHERE o.order_id = :id",
        id=first["order_id"],
    )
    assert [tuple(r[1:]) for r in cod] == [
        ("PENDING_PAYMENT", "PENDING", "COD", "PENDING", "120000.00")
    ]

    # 11. Đơn thứ hai: chuyển khoản thủ công, đang chờ.
    page.goto(f"{base}/product/demo-staging-sac-j")
    page.wait_for_selector("[data-add-sku]")
    page.click("[data-add-sku='DEMO-SAC-J']")
    page.wait_for_selector("#cartStatus.ok:not([hidden])")
    second = _place_order(page, base, "BANK_TRANSFER_MANUAL")
    assert page.inner_text("#paymentTitle").strip() == "Thanh toán: đang chờ"
    second_number = page.inner_text("#orderNumber").strip()

    # 12. Nhân viên thấy khách (Customer 360 có cả 2 đơn).
    found = staff(base, f"/api/admin/customers?phone={PHONE}")
    assert len(found) == 1
    detail = staff(base, f"/api/admin/customers/{found[0]['customer_id']}")
    assert sorted(o["payment_status"] for o in detail["orders"]) == ["PENDING", "PENDING"]

    # 13-15. Nhân viên thấy đơn + khoản thu trên trang admin và XÁC NHẬN đã nhận chuyển khoản.
    page.on("dialog", lambda d: d.accept(""))
    page.goto(f"{base}/admin-commerce.html")
    page.fill("#staffKey", STAFF_KEY)
    page.fill("#oQuery", second_number)
    page.click("#orderFilter button[type=submit]")
    page.locator(f"tr[data-order='{second_number}'] button").click()
    page.wait_for_selector("[data-payment='BANK_TRANSFER_MANUAL']")
    page.click("[data-payment='BANK_TRANSFER_MANUAL'] button:has-text('CONFIRM')")
    page.wait_for_function(
        "() => document.querySelector('#orderDetail').innerText.includes('Thanh toán: PAID')"
    )

    # 16. Trạng thái thanh toán đồng bộ sang trang đơn của khách.
    req = urllib.request.Request(
        f"{base}/api/orders/{second['order_id']}", headers={"X-Order-Token": second["token"]}
    )
    with urllib.request.urlopen(req) as r:
        view = json.loads(r.read())
    assert (view["payment_status"], view["payment"]["status"]) == ("PAID", "PAID")

    # 17. Kho đúng: SKU theo dõi bị GIỮ 1; SKU không theo dõi không có sổ.
    inv = staff(base, "/api/admin/inventory/DEMO-KINH-J")
    b = inv["balance"]
    assert (b["quantity_on_hand"], b["quantity_reserved"], b["quantity_available"]) == (5, 1, 4)
    assert [m["movement_type"] for m in inv["movements"]] == ["OPENING", "RESERVE"]

    # 18. Đổi giá sau khi đặt: ảnh chụp giá trong đơn KHÔNG đổi.
    staff(base, "/api/admin/variants/DEMO-KINH-J", "PATCH", {"sale_price": "99000.00"})
    assert q(
        "SELECT unit_price::text FROM order_items oi JOIN orders o ON o.id = oi.order_id "
        "WHERE o.order_id = :id",
        id=first["order_id"],
    ) == [("120000.00",)]

    # 19. Attribution: first-touch từ lead, đơn mang nguồn của lượt mua.
    assert q(
        "SELECT source, utm_campaign, ref, acquired_via FROM customer_acquisition WHERE customer_id = :c",
        c=customer_pk,
    ) == [("staging-test", "staging-acceptance", "KOL-JOURNEY", "LEAD")]
    assert q(
        "SELECT DISTINCT source, utm_campaign, ref FROM orders WHERE customer_id = :c",
        c=customer_pk,
    ) == [("staging-test", "staging-acceptance", "KOL-JOURNEY")]

    # 20. Quà vẫn phát được — và chỉ một lần.
    redeemed = staff(base, f"/api/gifts/{gift_code}/redeem", "POST", {})
    assert (redeemed["gift_status"], redeemed["already_redeemed"]) == ("REDEEMED", False)
    again = staff(base, f"/api/gifts/{gift_code}/redeem", "POST", {})
    assert again["already_redeemed"] is True

    # Toàn hành trình: event không PII, không lỗi console của ứng dụng.
    events = [e for e in payloads(page) if str(e.get("event", "")).startswith("vipphone_")]
    blob = json.dumps(events, ensure_ascii=False)
    assert PHONE not in blob and "Khách Hành Trình" not in blob
    names = {e["event"] for e in events}
    assert {
        "vipphone_recommendation_view",
        "vipphone_recommendation_click",
        "vipphone_product_view",
        "vipphone_add_to_cart",
        "vipphone_checkout_start",
        "vipphone_order_created",
        "vipphone_payment_pending",
    } <= names
    assert console_errors == []
