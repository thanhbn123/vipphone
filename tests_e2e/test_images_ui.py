"""E2E: ảnh sản phẩm hiện trên thẻ cửa hàng + trang chi tiết, không tràn ở mobile.

Ảnh được TẢI LÊN qua API admin rồi đọc lại qua trình duyệt — chứng minh cả đường
lưu lẫn đường phục vụ `/media/...` (cùng origin, qua CSP `img-src 'self'`).
"""

from __future__ import annotations

import io
import json
import urllib.request

import pytest
from PIL import Image

from tests.conftest import STAFF_KEY
from tests_e2e.test_g14_shop import api

pytestmark = [pytest.mark.e2e]


def _upload(base, product_id, alt):
    out = io.BytesIO()
    Image.new("RGB", (800, 600), (207, 32, 48)).save(out, "PNG")
    request = urllib.request.Request(
        f"{base}/api/admin/products/{product_id}/images?alt_text={urllib.request.quote(alt)}",
        data=out.getvalue(),
        method="POST",
        headers={"Content-Type": "image/png", "X-Staff-Key": STAFF_KEY},
    )
    with urllib.request.urlopen(request) as r:
        return json.loads(r.read())


@pytest.fixture
def product_with_image(live_server):
    product = api(
        live_server,
        "/api/admin/products",
        method="POST",
        key=STAFF_KEY,
        body={"name": "Ốp ảnh DEMO-STAGING", "slug": "demo-staging-anh", "category_code": "CASE"},
    )
    api(
        live_server,
        f"/api/admin/products/{product['product_id']}/variants",
        method="POST",
        key=STAFF_KEY,
        body={"sku": "DEMO-ANH", "variant_name": "Đỏ", "sale_price": "99000.00"},
    )
    _upload(live_server, product["product_id"], "Ốp đỏ mặt sau")
    return "demo-staging-anh"


@pytest.mark.parametrize("width", [320, 390, 1280])
def test_images_render_and_load(browser, live_server, product_with_image, width):
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    errors: list[str] = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    try:
        page.goto(f"{live_server}/shop")
        page.wait_for_selector(".product-thumb img")
        thumb = page.locator(".product-thumb img").first
        assert thumb.get_attribute("alt") == "Ốp đỏ mặt sau"
        page.wait_for_function(
            "() => { const i = document.querySelector('.product-thumb img'); "
            "return i && i.complete && i.naturalWidth === 800; }"
        )

        page.goto(f"{live_server}/product/{product_with_image}")
        page.wait_for_selector(".product-gallery img.primary")
        page.wait_for_function(
            "() => { const i = document.querySelector('.product-gallery img.primary'); "
            "return i && i.complete && i.naturalWidth === 800; }"
        )
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow == 0
        assert errors == []
    finally:
        context.close()
