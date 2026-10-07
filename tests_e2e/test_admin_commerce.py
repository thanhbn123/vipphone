"""E2E trang quản trị bán hàng `/admin-commerce.html` — nhân viên làm việc THẬT qua giao diện.

Luồng: khách đặt đơn (chuyển khoản) → nhân viên thấy đơn → chuyển trạng thái →
xác nhận thu tiền → thanh toán PAID; ghi nhập kho; đổi giá có lý do (lịch sử giá);
tải ảnh lên; xem báo cáo nguồn. Không lỗi console.
"""

from __future__ import annotations

import json
import urllib.request

import pytest
from PIL import Image

from tests.conftest import STAFF_KEY
from tests_e2e.test_g14_shop import api

pytestmark = [pytest.mark.e2e]


def _checkout(base) -> dict:
    cart = api(base, "/api/cart", method="POST")
    token = cart["cart_token"]

    def call(path, body, extra=None):
        req = urllib.request.Request(
            base + path,
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-Cart-Token": token, **(extra or {})},
        )
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    call(f"/api/cart/{cart['cart_id']}/items", {"sku": "DEMO-ADM", "quantity": 1})
    return call(
        "/api/checkout",
        {
            "cart_id": cart["cart_id"],
            "customer": {"full_name": "Khách DEMO-STAGING", "phone": "0901234567"},
            "shipping": {
                "recipient_name": "Khách DEMO-STAGING",
                "phone": "0901234567",
                "address_line": "1 Đường DEMO-STAGING",
                "province": "Hà Nội",
            },
            "payment_method": "BANK_TRANSFER_MANUAL",
            "attribution": {"source": "bni", "ref": "KOL-DEMO"},
        },
        {"Idempotency-Key": "e2e-admin-commerce-0001"},
    )


@pytest.fixture
def seeded(live_server):
    product = api(
        live_server,
        "/api/admin/products",
        method="POST",
        key=STAFF_KEY,
        body={
            "name": "Kính ADMIN DEMO-STAGING",
            "slug": "demo-staging-adm",
            "category_code": "SCREEN_PROTECTOR",
        },
    )
    api(
        live_server,
        f"/api/admin/products/{product['product_id']}/variants",
        method="POST",
        key=STAFF_KEY,
        body={
            "sku": "DEMO-ADM",
            "variant_name": "Bản demo",
            "sale_price": "50000.00",
            "stock_tracking": True,
        },
    )
    api(
        live_server,
        "/api/admin/inventory/DEMO-ADM/movements",
        method="POST",
        key=STAFF_KEY,
        body={"movement_type": "OPENING", "quantity": 5},
    )
    return _checkout(live_server)


def test_staff_operates_orders_inventory_prices_images_report(
    page, live_server, seeded, console_errors, tmp_path
):
    page.on("dialog", lambda d: d.accept("e2e"))
    page.goto(f"{live_server}/admin-commerce.html")
    page.fill("#staffKey", STAFF_KEY)
    page.click("#orderFilter button[type=submit]")
    row = page.locator(f"tr[data-order='{seeded['order_number']}']")
    row.wait_for()
    assert "PENDING_PAYMENT" in row.inner_text()

    # Chuyển trạng thái + xác nhận đã nhận chuyển khoản.
    row.locator("button").click()
    page.wait_for_selector("#orderDetail:not([hidden])")
    assert "ref=KOL-DEMO" in page.inner_text("#orderDetail")
    page.click("#orderDetail button:has-text('→ CONFIRMED')")
    page.wait_for_function(
        "() => document.querySelector('#orderDetail').innerText.includes('Trạng thái: CONFIRMED')"
    )
    page.click("[data-payment='BANK_TRANSFER_MANUAL'] button:has-text('CONFIRM')")
    page.wait_for_function(
        "() => document.querySelector('#orderDetail').innerText.includes('Thanh toán: PAID')"
    )

    # Kho: đơn đang giữ 1 → nhập thêm 10.
    page.click("[data-tab=inventory]")
    page.locator("tr[data-sku='DEMO-ADM'] button").click()
    page.wait_for_selector("#invDetail:not([hidden])")
    assert "tồn 5, giữ 1, bán được 4" in page.inner_text("#invTitle")
    page.select_option("#invType", "RECEIPT")
    page.fill("#invQty", "10")
    page.click("#invForm button[type=submit]")
    page.wait_for_function("() => document.querySelector('#invTitle').innerText.includes('tồn 15')")

    # Giá: đổi giá kèm lý do ⇒ lịch sử có dòng mới.
    page.click("[data-tab=products]")
    page.locator("tr[data-product='demo-staging-adm'] button").click()
    page.wait_for_selector("#prodDetail:not([hidden])")
    page.fill("#priceNew", "55000.00")
    page.fill("#priceReason", "Điều chỉnh E2E")
    page.click("#priceForm button[type=submit]")
    page.wait_for_function(
        "() => document.querySelector('#priceRows').innerText.includes('Điều chỉnh E2E')"
    )

    # Ảnh: tải lên qua ô chọn tệp thật.
    image_path = tmp_path / "demo.png"
    Image.new("RGB", (320, 240), (10, 120, 200)).save(image_path, "PNG")
    page.set_input_files("#imageFile", str(image_path))
    page.fill("#imageAlt", "Kính DEMO mặt trước")
    page.click("#imageForm button[type=submit]")
    page.wait_for_selector(".admin-image img")
    assert "ẢNH CHÍNH" in page.inner_text("#imageList")

    # Báo cáo nguồn: referrer ra doanh thu.
    page.click("[data-tab=report]")
    page.select_option("#repDim", "ref")
    page.click("#repForm button[type=submit]")
    page.wait_for_function(
        "() => document.querySelector('#repRows').innerText.includes('KOL-DEMO')"
    )
    assert "50.000,00 đ" in page.inner_text("#repRows")
    assert console_errors == []


def test_admin_commerce_without_key_shows_auth_error(page, live_server, console_errors):
    page.goto(f"{live_server}/admin-commerce.html")
    page.click("#orderFilter button[type=submit]")
    page.wait_for_selector("#adminError:not([hidden])")
    assert "Khoá nhân viên" in page.inner_text("#adminError")
    # 401 là lỗi mạng mà trình duyệt tự ghi console — không phải lỗi của mã trang.
    assert all("401" in e for e in console_errors), console_errors
