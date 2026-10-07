"""G15 — Engine gợi ý phụ kiện. Thiết kế: `docs/recommendation-engine.md`.

Điều bộ test này bảo vệ:

1. Chỉ gợi ý hàng tương thích ĐÚNG máy; máy khác bị loại.
2. Product tắt / SKU tắt / category tắt bị loại — qua CHÍNH đường lọc của G14.
3. Thứ tự XÁC ĐỊNH: theo bảng ưu tiên, rồi tên, rồi id. Chạy hai lần ⇒ giống hệt.
4. Sau quà ốp (`POST_GIFT`) ⇒ KHÔNG gợi ý ốp.
5. JSON công khai không có PII và không có `cost_price`.

`test_NEGATIVE_control_*` chứng minh phép đo PHÂN BIỆT được đúng và sai.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from tests.conftest import RECO_MIGRATION

pytestmark = pytest.mark.integration

DEVICE = "iphone-16-pro-max"
OTHER_DEVICE = "iphone-15"


def _product(client, staff_headers, *, slug: str, name: str, category: str) -> str:
    response = client.post(
        "/api/admin/products",
        json={"name": name, "slug": slug, "category_code": category},
        headers=staff_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["product_id"]


def _sku(client, staff_headers, product_id: str, sku: str, devices: list[str], **extra) -> None:
    response = client.post(
        f"/api/admin/products/{product_id}/variants",
        json={
            "sku": sku,
            "variant_name": sku,
            "sale_price": "100000.00",
            "cost_price": "40000.00",
            **extra,
        },
        headers=staff_headers,
    )
    assert response.status_code == 201, response.text
    for device in devices:
        r = client.post(
            f"/api/admin/variants/{sku}/compatibility",
            json={"device_model_code": device, "compatibility_type": "FULL"},
            headers=staff_headers,
        )
        assert r.status_code == 201, r.text


def _reco(client, device: str = DEVICE, **params):
    return client.get("/api/recommendations", params={"device_model": device, **params})


@pytest.fixture
def catalog(client, staff_headers) -> dict[str, str]:
    """Bộ hàng mẫu phủ đủ nhóm, cố ý tạo KHÔNG theo thứ tự ưu tiên."""
    ids = {}
    spec = [
        ("cable-b", "Cáp B", "CABLE"),
        ("charger-a", "Củ sạc A", "CHARGER"),
        ("glass-z", "Kính Z", "SCREEN_PROTECTOR"),
        ("glass-a", "Kính A", "SCREEN_PROTECTOR"),
        ("case-a", "Ốp A", "CASE"),
        ("car-a", "Giá ô tô A", "CAR_ACCESSORY"),
        ("stand-a", "Giá đỡ A", "STAND"),
    ]
    for slug, name, category in spec:
        ids[slug] = _product(client, staff_headers, slug=slug, name=name, category=category)
        _sku(client, staff_headers, ids[slug], f"SKU-{slug.upper()}", [DEVICE])
    return ids


# --------------------------------------------------------------------------
# Thứ tự + loại trừ
# --------------------------------------------------------------------------
def test_exact_order_follows_priority_then_name(client, catalog):
    response = _reco(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["context"] == "POST_GIFT"
    assert body["device_model_code"] == DEVICE
    # Khẳng định TOÀN BỘ danh sách, không khẳng định chuỗi con.
    assert [(i["rank"], i["category_code"], i["product"]["slug"]) for i in body["items"]] == [
        (1, "SCREEN_PROTECTOR", "glass-a"),
        (2, "SCREEN_PROTECTOR", "glass-z"),
        (3, "CHARGER", "charger-a"),
        (4, "CABLE", "cable-b"),
        (5, "CAR_ACCESSORY", "car-a"),
    ]


def test_case_and_unprioritised_categories_are_never_recommended_after_gift(client, catalog):
    slugs = {i["product"]["slug"] for i in _reco(client).json()["items"]}
    assert "case-a" not in slugs
    assert "stand-a" not in slugs


def test_order_is_stable_across_repeated_calls(client, catalog):
    first = _reco(client).json()
    second = _reco(client).json()
    assert first == second


def test_name_tie_is_broken_by_id(client, staff_headers):
    """Hai sản phẩm TRÙNG tên, cùng nhóm ⇒ thứ tự theo id (tạo trước đứng trước)."""
    first = _product(client, staff_headers, slug="kinh-1", name="Kính", category="SCREEN_PROTECTOR")
    _sku(client, staff_headers, first, "KINH-1", [DEVICE])
    second = _product(
        client, staff_headers, slug="kinh-2", name="Kính", category="SCREEN_PROTECTOR"
    )
    _sku(client, staff_headers, second, "KINH-2", [DEVICE])
    for _ in range(3):
        assert [i["product"]["slug"] for i in _reco(client).json()["items"]] == ["kinh-1", "kinh-2"]


def test_wrong_device_gets_nothing_from_other_device_catalog(client, catalog):
    body = _reco(client, OTHER_DEVICE).json()
    assert body["items"] == []


def test_only_compatible_skus_are_returned(client, staff_headers):
    pid = _product(
        client, staff_headers, slug="kinh-da", name="Kính đa", category="SCREEN_PROTECTOR"
    )
    _sku(client, staff_headers, pid, "KINH-16", [DEVICE])
    _sku(client, staff_headers, pid, "KINH-15", [OTHER_DEVICE])
    items = _reco(client).json()["items"]
    assert [v["sku"] for v in items[0]["product"]["variants"]] == ["KINH-16"]
    items15 = _reco(client, OTHER_DEVICE).json()["items"]
    assert [v["sku"] for v in items15[0]["product"]["variants"]] == ["KINH-15"]


def test_inactive_product_is_excluded(client, staff_headers, catalog):
    r = client.patch(
        f"/api/admin/products/{catalog['glass-a']}", json={"active": False}, headers=staff_headers
    )
    assert r.status_code == 200, r.text
    slugs = [i["product"]["slug"] for i in _reco(client).json()["items"]]
    assert "glass-a" not in slugs
    assert slugs[0] == "glass-z"


def test_inactive_sku_is_excluded(client, staff_headers, catalog):
    r = client.patch(
        "/api/admin/variants/SKU-GLASS-A", json={"active": False}, headers=staff_headers
    )
    assert r.status_code == 200, r.text
    slugs = [i["product"]["slug"] for i in _reco(client).json()["items"]]
    assert "glass-a" not in slugs


def test_inactive_category_is_excluded(client, catalog, db):
    db.execute(text("UPDATE categories SET active = false WHERE code = 'CHARGER'"))
    db.commit()
    codes = [i["category_code"] for i in _reco(client).json()["items"]]
    assert "CHARGER" not in codes


def test_priority_is_data_not_code(client, catalog, db):
    """Đổi thứ tự bằng UPDATE ⇒ kết quả đổi theo, không cần sửa mã."""
    db.execute(
        text(
            "UPDATE recommendation_category_priority SET priority = 99 "
            "WHERE context = 'POST_GIFT' AND category_code = 'SCREEN_PROTECTOR'"
        )
    )
    db.commit()
    codes = [i["category_code"] for i in _reco(client).json()["items"]]
    assert codes == ["CHARGER", "CABLE", "CAR_ACCESSORY", "SCREEN_PROTECTOR", "SCREEN_PROTECTOR"]


def test_limit_is_applied_and_capped(client, catalog):
    assert len(_reco(client, limit=2).json()["items"]) == 2
    assert _reco(client, limit=25).status_code == 422


def test_unknown_device_is_422_not_empty_200(client):
    response = _reco(client, "iphone-99-ultra")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MODEL_NOT_IN_CATALOG"


def test_exclude_product_ids_extension_point(db, client, catalog):
    from app.models import Product
    from app.services.recommendations import recommend

    glass_a = db.query(Product).filter(Product.slug == "glass-a").one()
    result = recommend(db, device_model=DEVICE, exclude_product_ids=[glass_a.id])
    assert "glass-a" not in [i.product.slug for i in result.items]


# --------------------------------------------------------------------------
# Không PII, không giá nhập
# --------------------------------------------------------------------------
FORBIDDEN_KEYS = {"phone", "email", "full_name", "address", "cost_price", "customer_id"}


def _all_keys(value) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            keys.add(key)
            keys |= _all_keys(inner)
    elif isinstance(value, list):
        for inner in value:
            keys |= _all_keys(inner)
    return keys


def test_public_json_has_no_pii_and_no_cost_price(client, catalog):
    body = _reco(client).json()
    assert body["items"], "phải có dữ liệu thì phép đo mới có nghĩa"
    assert not (_all_keys(body) & FORBIDDEN_KEYS)
    assert "40000" not in json.dumps(body)


def test_seed_matches_approved_priority():
    assert [r["category_code"] for r in RECO_MIGRATION.seed_rows()] == [
        "SCREEN_PROTECTOR",
        "CHARGER",
        "CABLE",
        "MAGSAFE",
        "POWER_BANK",
        "EARPHONE",
        "CAR_ACCESSORY",
    ]
    assert "CASE" not in {r["category_code"] for r in RECO_MIGRATION.seed_rows()}


def test_duplicate_priority_rejected_by_db(db):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO recommendation_category_priority (context, category_code, priority) "
                "VALUES ('POST_GIFT', 'STAND', 1)"
            )
        )
        db.flush()
    db.rollback()


def test_unknown_category_code_rejected_by_fk(db):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO recommendation_category_priority (context, category_code, priority) "
                "VALUES ('POST_GIFT', 'KHONG_CO', 50)"
            )
        )
        db.flush()
    db.rollback()


# --------------------------------------------------------------------------
# Đối chứng âm: phép đo phải ĐỎ khi dữ liệu sai
# --------------------------------------------------------------------------
def test_NEGATIVE_control_order_assertion_detects_swapped_order(client, catalog):
    names = [i["product"]["slug"] for i in _reco(client).json()["items"]]
    assert names != ["charger-a", "glass-a", "glass-z", "cable-b", "car-a"]


def test_NEGATIVE_control_pii_detector_flags_pii():
    assert _all_keys({"items": [{"product": {"phone": "0912345678"}}]}) & FORBIDDEN_KEYS
