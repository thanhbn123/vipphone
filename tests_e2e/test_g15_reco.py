"""E2E trình duyệt THẬT cho G15 — gợi ý phụ kiện sau khi nhận quà.

Đo những điều tầng API không đo được:

1. Trang thành công **vẽ gợi ý từ API**, đúng thứ tự, KHÔNG có ốp (CASE).
2. CTA trỏ đúng `/shop?category=...&device_model=<mã máy>`.
3. `dataLayer` có `vipphone_recommendation_view` / `_click` / `vipphone_product_view`
   và **không** chứa PII (tên, SĐT, email, địa chỉ) ở bất kỳ payload nào.
4. Không lỗi console / CSP; không tràn ngang ở 320px.
"""

from __future__ import annotations

import json

import pytest

from tests_e2e.test_funnel import fill_lead_form, open_landing, submit_and_wait
from tests_e2e.test_g14_shop import api

pytestmark = [pytest.mark.e2e]

DEVICE = "iphone-16-pro-max"
NAME = "Khách DEMO-STAGING"
PHONE = "0912345678"

#: Bộ ghi payload ĐẦY ĐỦ (không chỉ tên event), bền qua điều hướng.
RECORDER = """
(function () {
  window.dataLayer = window.dataLayer || [];
  var KEY = '__e2e_payloads__';
  var original = window.dataLayer.push.bind(window.dataLayer);
  window.dataLayer.push = function () {
    try {
      var list = JSON.parse(sessionStorage.getItem(KEY) || '[]');
      for (var i = 0; i < arguments.length; i++) list.push(arguments[i]);
      sessionStorage.setItem(KEY, JSON.stringify(list));
    } catch (e) {}
    return original.apply(null, arguments);
  };
})();
"""


def _product(base, key, slug, name, category, sku, device=DEVICE):
    product = api(
        base,
        "/api/admin/products",
        method="POST",
        key=key,
        body={"name": name, "slug": slug, "category_code": category},
    )
    api(
        base,
        f"/api/admin/products/{product['product_id']}/variants",
        method="POST",
        key=key,
        body={"sku": sku, "variant_name": "Bản demo", "sale_price": "150000.00"},
    )
    api(
        base,
        f"/api/admin/variants/{sku}/compatibility",
        method="POST",
        key=key,
        body={"device_model_code": device, "compatibility_type": "FULL"},
    )


@pytest.fixture
def reco_catalog(live_server):
    from tests.conftest import STAFF_KEY

    _product(live_server, STAFF_KEY, "demo-staging-sac", "Củ sạc DEMO", "CHARGER", "DEMO-SAC")
    _product(
        live_server, STAFF_KEY, "demo-staging-kinh", "Kính DEMO", "SCREEN_PROTECTOR", "DEMO-KINH"
    )
    _product(live_server, STAFF_KEY, "demo-staging-op", "Ốp DEMO", "CASE", "DEMO-OP")
    _product(
        live_server,
        STAFF_KEY,
        "demo-staging-kinh15",
        "Kính 15 DEMO",
        "SCREEN_PROTECTOR",
        "DEMO-KINH15",
        device="iphone-15",
    )


@pytest.fixture
def rec_page(browser, console_errors):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.add_init_script(RECORDER)
    page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    try:
        yield page
    finally:
        context.close()


def payloads(page) -> list[dict]:
    return page.evaluate("JSON.parse(sessionStorage.getItem('__e2e_payloads__') || '[]')")


def _to_success(page, base):
    open_landing(page, base)
    fill_lead_form(page, name=NAME, phone=PHONE, model=DEVICE)
    submit_and_wait(page)
    page.wait_for_selector("#recoSection:not([hidden])", timeout=20_000)


def test_success_page_shows_device_recommendations_without_case(
    rec_page, live_server, reco_catalog, console_errors
):
    _to_success(rec_page, live_server)
    names = rec_page.locator("#recoList .product-name").all_inner_texts()
    assert names == ["Kính DEMO", "Củ sạc DEMO"]

    hrefs = {
        cta: rec_page.get_attribute(f"#{cta}", "href")
        for cta in ("recoCtaGlass", "recoCtaCharge", "recoCtaAll")
    }
    assert hrefs == {
        "recoCtaGlass": f"/shop?category=SCREEN_PROTECTOR&device_model={DEVICE}",
        "recoCtaCharge": f"/shop?category=CHARGER&device_model={DEVICE}",
        "recoCtaAll": f"/shop?device_model={DEVICE}",
    }
    assert console_errors == []


def test_tracking_events_fire_and_carry_no_pii(rec_page, live_server, reco_catalog, console_errors):
    _to_success(rec_page, live_server)
    rec_page.click("#recoList .reco-item[data-reco-rank='1'] .product-name a")
    rec_page.wait_for_url("**/product/demo-staging-kinh")
    rec_page.wait_for_selector("#productDetail:not([hidden])", timeout=20_000)

    events = payloads(rec_page)
    names = [e.get("event") for e in events]
    for required in (
        "vipphone_recommendation_view",
        "vipphone_recommendation_click",
        "vipphone_product_view",
    ):
        assert required in names, names

    click = next(e for e in events if e.get("event") == "vipphone_recommendation_click")
    assert click["category"] == "SCREEN_PROTECTOR"
    assert click["sku"] == "DEMO-KINH"
    assert click["device_model_code"] == DEVICE
    assert click["rank"] == 1

    reco_events = [
        e for e in events if e.get("event", "").startswith(("vipphone_reco", "vipphone_product"))
    ]
    blob = json.dumps(reco_events, ensure_ascii=False)
    # GIÁ TRỊ PII thật của khách này không được xuất hiện ở đâu cả.
    for value in (NAME, PHONE):
        assert value not in blob, value
    # TÊN TRƯỜNG PII: so theo KHOÁ, không theo chuỗi con — `iphone-16-pro-max`
    # chứa chữ "phone" nên so chuỗi con sẽ báo động giả (đã dính khi viết bài này).
    keys = {key for event in reco_events for key in event}
    assert not keys & {"phone", "email", "full_name", "address", "customer_id"}, keys
    assert console_errors == []


def test_no_horizontal_overflow_on_320px(browser, live_server, reco_catalog):
    context = browser.new_context(viewport={"width": 320, "height": 800})
    page = context.new_page()
    try:
        _to_success(page, live_server)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow == 0
    finally:
        context.close()
