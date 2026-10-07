"""E2E trình duyệt THẬT cho G14 — `/shop` và `/product/{slug}`.

VÌ SAO CẦN LỚP NÀY: `tests/test_product_catalog.py` đo tầng API. Nó KHÔNG chứng
minh được ba điều, mà cả ba đều là yêu cầu của gate:

1. Trang cửa hàng **vẽ ra sản phẩm từ API** — chứ không hard-code trong HTML.
2. **Không có lỗi console / vi phạm CSP** khi tải trang (CSP nghiêm `script-src
   'self'` sẽ chặn mọi script nội tuyến, và trình duyệt mới là thứ nói ra điều đó).
3. **Không tràn ngang ở 320px** — đo bằng bố cục thật, không đoán từ CSS.

Dữ liệu tạo ra ở đây là **demo-staging**: tên có chữ `DEMO-STAGING`, slug có tiền
tố `demo-staging-`. Không có sản phẩm thật nào bị bịa ra.
"""

from __future__ import annotations

import json
import urllib.request
import uuid

import pytest

DEMO_NAME = "Ốp DEMO-STAGING (dữ liệu test)"
DEMO_PRICE = "250000.00"
DEMO_COMPARE = "300000.00"


def api(base_url: str, path: str, *, method: str = "GET", key: str | None = None, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(base_url + path, data=data, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    if key:
        request.add_header("X-Staff-Key", key)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


@pytest.fixture
def staff_key() -> str:
    from tests.conftest import STAFF_KEY

    return STAFF_KEY


@pytest.fixture
def demo_product(live_server, staff_key) -> dict:
    """Tạo một sản phẩm demo-staging + 1 SKU + 1 khai báo tương thích, qua API admin."""
    slug = f"demo-staging-{uuid.uuid4().hex[:8]}"
    product = api(
        live_server,
        "/api/admin/products",
        method="POST",
        key=staff_key,
        body={
            "name": DEMO_NAME,
            "slug": slug,
            "category_code": "CASE",
            "brand": "DEMO-STAGING",
            "description": "Sản phẩm tạo tự động cho test E2E G14.",
        },
    )
    sku = f"DEMO-{uuid.uuid4().hex[:8].upper()}"
    api(
        live_server,
        f"/api/admin/products/{product['product_id']}/variants",
        method="POST",
        key=staff_key,
        body={
            "sku": sku,
            "variant_name": "Bản demo",
            "color": "Đen",
            "sale_price": DEMO_PRICE,
            "compare_at_price": DEMO_COMPARE,
            "currency": "VND",
        },
    )
    api(
        live_server,
        f"/api/admin/variants/{sku}/compatibility",
        method="POST",
        key=staff_key,
        body={"device_model_code": "iphone-16-pro-max", "compatibility_type": "FULL"},
    )
    return {"slug": slug, "sku": sku, "product_id": product["product_id"]}


def test_shop_renders_product_created_through_admin_api(
    page, live_server, demo_product, console_errors
):
    """ĐO BẰNG TRÌNH DUYỆT THẬT: sản phẩm tạo qua API admin ⇒ hiện trên `/shop`.

    Kèm hai phép đo không thể làm bằng API: **0 lỗi console** (CSP không chặn gì,
    không có vi phạm `script-src 'self'`) và nhãn trạng thái là "Còn hàng" —
    KHÔNG kèm con số tồn kho nào.
    """
    page.goto(live_server + "/shop", wait_until="load")
    page.wait_for_selector(".product-card", timeout=20_000)

    assert DEMO_NAME in page.inner_text("#productList")
    assert page.inner_text(".badge") == "Còn hàng"
    # Giá hiển thị theo định dạng Việt Nam, đọc từ API chứ không hard-code.
    assert "250.000" in page.inner_text(".product-price")
    assert page.inner_text("#shopCount").startswith("Tìm thấy 1 sản phẩm")
    assert console_errors == [], f"trang cửa hàng có lỗi console/CSP: {console_errors}"


def test_product_detail_shows_no_quantity_anywhere(page, live_server, demo_product):
    page.goto(live_server + f"/product/{demo_product['slug']}", wait_until="load")
    page.wait_for_function(
        "() => document.getElementById('productTitle').textContent.trim().length > 0",
        timeout=20_000,
    )

    body = page.inner_text("body")
    assert DEMO_NAME in body
    assert "Còn hàng" in body
    assert demo_product["sku"] in body
    assert "iphone-16-pro-max" in body
    # KHÔNG có con số tồn kho nào — chưa có inventory engine.
    for forbidden in ("còn 1", "còn 2", "Số lượng:", "tồn kho:"):
        assert forbidden.lower() not in body.lower(), f"UI bịa số lượng tồn kho: {forbidden!r}"


def test_detail_shows_out_of_stock_when_sku_deactivated(page, live_server, staff_key, demo_product):
    """Tắt SKU ⇒ trang chi tiết nói "Hết hàng" — không bịa số, không giấu sản phẩm."""
    api(
        live_server,
        f"/api/admin/variants/{demo_product['sku']}",
        method="PATCH",
        key=staff_key,
        body={"active": False},
    )
    page.goto(live_server + f"/product/{demo_product['slug']}", wait_until="load")
    page.wait_for_selector("#productAvailability", timeout=20_000)
    page.wait_for_function(
        "() => document.getElementById('productAvailability').textContent.trim() === 'Hết hàng'",
        timeout=20_000,
    )
    assert "không có phiên bản nào đang bán" in page.inner_text("#productBody")


def test_detail_of_deactivated_product_says_not_found(page, live_server, staff_key, demo_product):
    """Sản phẩm đã tắt ⇒ 404 ⇒ trang nói KHÔNG TÌM THẤY, không hiện hàng giả."""
    api(
        live_server,
        f"/api/admin/products/{demo_product['product_id']}",
        method="PATCH",
        key=staff_key,
        body={"active": False},
    )
    page.goto(live_server + f"/product/{demo_product['slug']}", wait_until="load")
    page.wait_for_selector("#productError:not([hidden])", timeout=20_000)
    assert "Không tìm thấy" in page.inner_text("#productError")
    assert page.is_hidden("#productDetail")


def test_shop_filters_by_device_in_the_browser(page, live_server, demo_product):
    """Chọn dòng máy trên giao diện ⇒ danh sách lọc thật, và URL mang bộ lọc."""
    page.goto(live_server + "/shop", wait_until="load")
    page.wait_for_function(
        "() => document.querySelectorAll('#filterDevice option').length > 1", timeout=20_000
    )
    page.select_option("#filterDevice", "iphone-16-pro-max")
    page.click("#filterSubmit")
    page.wait_for_function(
        "() => document.getElementById('shopCount').textContent.includes('Tìm thấy')",
        timeout=20_000,
    )
    assert "device_model=iphone-16-pro-max" in page.url
    assert DEMO_NAME in page.inner_text("#productList")

    # Chọn máy KHÔNG tương thích ⇒ danh sách rỗng, KHÔNG hiện sản phẩm.
    page.select_option("#filterDevice", "iphone-11")
    page.click("#filterSubmit")
    page.wait_for_function(
        "() => document.getElementById('shopCount').textContent.includes('Không có')",
        timeout=20_000,
    )
    assert DEMO_NAME not in page.inner_text("#productList")


def test_shop_does_not_overflow_on_a_320px_screen(page, live_server, demo_product):
    """Mobile-first: KHÔNG tràn ngang ở 320px. Đo bằng bố cục thật."""
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_server + "/shop", wait_until="load")
    page.wait_for_selector(".product-card", timeout=20_000)

    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, f"tràn ngang {overflow}px ở 320px"

    page.goto(live_server + f"/product/{demo_product['slug']}", wait_until="load")
    page.wait_for_selector("#productDetail:not([hidden])", timeout=20_000)
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, f"trang chi tiết tràn ngang {overflow}px ở 320px"
