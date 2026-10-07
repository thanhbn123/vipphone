"""G13 — Nền móng khách hàng. ADR: `docs/adr/0002-customer-identity.md`.

Điều quan trọng nhất bộ test này bảo vệ: **danh tính = SĐT chuẩn hoá**, và
**liên kết khách không được làm hỏng luồng quà tặng**.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import Customer, CustomerAcquisition, CustomerDevice, Lead
from app.phone import normalize_phone

# V6: cùng lỗi như `test_product_catalog.py` — 20 bài DB-backed nhưng thiếu dấu,
# nên bước CI `pytest -m integration` không chạy bài nào của tệp này.
pytestmark = pytest.mark.integration


def _lead_by_gift(db, gift_code):
    return db.execute(select(Lead).where(Lead.gift_code == gift_code)).scalar_one()


def _customer_of(db, gift_code):
    lead = _lead_by_gift(db, gift_code)
    assert lead.customer_id is not None, "lead phải được gắn customer"
    return db.execute(select(Customer).where(Customer.id == lead.customer_id)).scalar_one()


# --------------------------------------------------------------------------
# Tạo khách
# --------------------------------------------------------------------------
def test_new_lead_creates_customer(client, valid_lead_payload, db):
    r = client.post("/api/leads", json=valid_lead_payload)
    assert r.status_code == 201, r.text
    customer = _customer_of(db, r.json()["gift_code"])
    assert customer.phone_normalized == normalize_phone(valid_lead_payload["phone"])
    assert customer.status == "ACTIVE"
    assert customer.marketing_consent is True  # payload có consent=true


def test_same_phone_reuses_customer(client, valid_lead_payload, db):
    a = client.post(
        "/api/leads",
        json={**valid_lead_payload, "phone": "0911000002", "iphone_model": "iphone-16"},
    )
    b = client.post(
        "/api/leads",
        json={
            **valid_lead_payload,
            "iphone_model": "iphone-17-pro",
            "phone": "0911000002",
        },
    )
    assert (a.status_code, b.status_code) == (201, 201), (a.text, b.text)

    ca, cb = _customer_of(db, a.json()["gift_code"]), _customer_of(db, b.json()["gift_code"])
    assert ca.id == cb.id, "cùng SĐT PHẢI về cùng một khách"
    assert (
        db.execute(
            select(func.count())
            .select_from(Customer)
            .where(Customer.phone_normalized == "0911000002")
        ).scalar_one()
        == 1
    ), "cùng SĐT chỉ được có MỘT khách"


def test_phone_formatting_variants_reuse_customer(client, valid_lead_payload, db):
    """SĐT gõ khác nhau (khoảng trắng, +84, dấu chấm) vẫn phải là MỘT khách."""
    base = valid_lead_payload["phone"]
    variants = [base, f" {base} ", f"+84{base[1:]}"]
    codes = []
    for i, phone in enumerate(variants):
        r = client.post(
            "/api/leads",
            json={
                **valid_lead_payload,
                "phone": phone,
                "iphone_model": ["iphone-16", "iphone-17", "iphone-17-pro"][i],
            },
        )
        assert r.status_code == 201, r.text
        codes.append(r.json()["gift_code"])
    ids = {_customer_of(db, c).id for c in codes}
    assert len(ids) == 1, f"mọi cách gõ phải về cùng khách, nhận được {len(ids)}"


def test_multiple_leads_keep_provenance(client, valid_lead_payload, db):
    """Nhiều lead -> một khách, nhưng MỖI lead giữ nguyên vết của nó."""
    r1 = client.post(
        "/api/leads",
        json={**valid_lead_payload, "phone": "0911000004", "iphone_model": "iphone-16"},
    )
    r2 = client.post(
        "/api/leads",
        json={
            **valid_lead_payload,
            "phone": "0911000004",
            "iphone_model": "iphone-17-pro",
            "source": "tiktok",
        },
    )
    c = _customer_of(db, r1.json()["gift_code"])
    leads = db.execute(select(Lead).where(Lead.customer_id == c.id)).scalars().all()
    assert len(leads) == 2
    assert {le.source for le in leads} == {"facebook", "tiktok"} or len(
        {le.source for le in leads}
    ) == 2
    # gift code khác nhau -> không ghi đè vết
    assert r1.json()["gift_code"] != r2.json()["gift_code"]


# --------------------------------------------------------------------------
# Thiết bị
# --------------------------------------------------------------------------
def test_device_created_with_model_code(client, valid_lead_payload, db):
    r = client.post(
        "/api/leads",
        json={**valid_lead_payload, "phone": "0911000005", "iphone_model": "iphone-16"},
    )
    c = _customer_of(db, r.json()["gift_code"])
    devices = (
        db.execute(select(CustomerDevice).where(CustomerDevice.customer_id == c.id)).scalars().all()
    )
    assert len(devices) == 1
    assert devices[0].model_code == "iphone-16", "phải tra được model_code từ tên hiển thị"
    assert devices[0].is_primary is True


def test_primary_device_follows_newest_lead(client, valid_lead_payload, db):
    """Máy chính = máy của lead MỚI NHẤT, và ĐÚNG MỘT máy chính."""
    client.post(
        "/api/leads",
        json={**valid_lead_payload, "phone": "0911000006", "iphone_model": "iphone-16"},
    )
    r2 = client.post(
        "/api/leads",
        json={**valid_lead_payload, "phone": "0911000006", "iphone_model": "iphone-17-pro"},
    )
    c = _customer_of(db, r2.json()["gift_code"])
    devices = (
        db.execute(select(CustomerDevice).where(CustomerDevice.customer_id == c.id)).scalars().all()
    )
    primary = [d for d in devices if d.is_primary]
    assert len(primary) == 1, f"phải ĐÚNG MỘT máy chính, có {len(primary)}"
    assert primary[0].model_code == "iphone-17-pro"


def test_duplicate_device_not_duplicated(client, valid_lead_payload, db):
    """Cùng khách, cùng model, hai lead -> vẫn MỘT dòng thiết bị."""
    client.post(
        "/api/leads",
        json={**valid_lead_payload, "phone": "0911000007", "iphone_model": "iphone-16"},
    )
    r2 = client.post(
        "/api/leads",
        json={**valid_lead_payload, "phone": "0911000007", "iphone_model": "iphone-16"},
    )
    c = _customer_of(db, r2.json()["gift_code"])
    n = db.execute(
        select(func.count()).select_from(CustomerDevice).where(CustomerDevice.customer_id == c.id)
    ).scalar_one()
    assert n == 1


# --------------------------------------------------------------------------
# Nguồn gốc + consent
# --------------------------------------------------------------------------
def test_acquisition_is_first_touch_and_not_overwritten(client, valid_lead_payload, db):
    r1 = client.post(
        "/api/leads",
        json={
            **valid_lead_payload,
            "phone": "0911000008",
            "iphone_model": "iphone-16",
            "source": "facebook",
            "utm_campaign": "c1",
        },
    )
    client.post(
        "/api/leads",
        json={
            **valid_lead_payload,
            "phone": "0911000008",
            "iphone_model": "iphone-17-pro",
            "source": "tiktok",
            "utm_campaign": "c2",
        },
    )
    c = _customer_of(db, r1.json()["gift_code"])
    acq = (
        db.execute(select(CustomerAcquisition).where(CustomerAcquisition.customer_id == c.id))
        .scalars()
        .all()
    )
    assert len(acq) == 1, "first-touch: đúng MỘT dòng mỗi khách"
    assert acq[0].source == "facebook", "lead sau KHÔNG được ghi đè nguồn gốc"
    assert acq[0].utm_campaign == "c1"
    assert acq[0].first_gift_code == r1.json()["gift_code"]


def test_customer_name_not_overwritten_by_later_lead(client, valid_lead_payload, db):
    """Không ghi đè lịch sử: lead sau ghi tên khác thì GIỮ tên gốc."""
    r1 = client.post(
        "/api/leads",
        json={
            **valid_lead_payload,
            "phone": "0911000009",
            "iphone_model": "iphone-16",
            "full_name": "Tên Gốc",
        },
    )
    client.post(
        "/api/leads",
        json={
            **valid_lead_payload,
            "phone": "0911000009",
            "iphone_model": "iphone-17-pro",
            "full_name": "Tên Khác",
        },
    )
    assert _customer_of(db, r1.json()["gift_code"]).full_name == "Tên Gốc"


# --------------------------------------------------------------------------
# Không làm hỏng luồng quà tặng
# --------------------------------------------------------------------------
def test_gift_flow_unchanged(client, valid_lead_payload):
    r = client.post("/api/leads", json=valid_lead_payload)
    assert r.status_code == 201
    body = r.json()
    assert body["gift_status"] == "NEW"
    assert body["gift_code"].startswith("VIP-")
    assert body["duplicate"] is False


def test_duplicate_lead_still_returns_same_gift(client, valid_lead_payload):
    a = client.post("/api/leads", json=valid_lead_payload)
    b = client.post("/api/leads", json=valid_lead_payload)
    assert a.json()["gift_code"] == b.json()["gift_code"]
    assert b.json()["duplicate"] is True


def test_redeem_still_works(client, valid_lead_payload, staff_headers):
    code = client.post("/api/leads", json=valid_lead_payload).json()["gift_code"]
    r = client.post(f"/api/gifts/{code}/redeem", json={}, headers=staff_headers)
    assert r.status_code == 200
    assert r.json()["gift_status"] == "REDEEMED"


# ==========================================================================
# API quản trị khách hàng + KIỂM SOÁT ÂM (chứng minh test biết đỏ)
# ==========================================================================
def test_admin_list_requires_staff(client):
    """Không có khoá nhân viên -> phải 401. Đây là chốt chống DÒ khách."""
    assert client.get("/api/admin/customers").status_code == 401
    assert (
        client.get("/api/admin/customers/00000000-0000-0000-0000-000000000000").status_code == 401
    )


def test_admin_list_rejects_wrong_staff_key(client):
    r = client.get("/api/admin/customers", headers={"X-Staff-Key": "sai-khoa"})
    assert r.status_code == 401


def test_admin_can_list_and_view_customer(client, valid_lead_payload, db, staff_headers):
    r = client.post(
        "/api/leads",
        json={**valid_lead_payload, "phone": "0911000020", "iphone_model": "iphone-17-pro"},
    )
    customer = _customer_of(db, r.json()["gift_code"])

    lst = client.get("/api/admin/customers", headers=staff_headers)
    assert lst.status_code == 200, lst.text
    assert any(c["customer_id"] == str(customer.customer_id) for c in lst.json())

    detail = client.get(f"/api/admin/customers/{customer.customer_id}", headers=staff_headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["phone_masked"] != customer.phone_normalized, "SĐT phải được che"
    assert len(body["devices"]) == 1
    assert body["devices"][0]["model_code"] == "iphone-17-pro"
    assert body["acquisition"] is not None
    assert len(body["gift_history"]) == 1
    assert body["orders"] == [], "G16 chưa làm -> trả rỗng, KHÔNG bịa đơn hàng"


def test_admin_customer_detail_404_for_unknown(client, staff_headers):
    r = client.get(
        "/api/admin/customers/00000000-0000-0000-0000-000000000000", headers=staff_headers
    )
    assert r.status_code == 404


def test_no_public_customer_endpoint_exists(client):
    """Chốt chống DÒ: các đường công khai hay bị mở nhầm phải KHÔNG tồn tại."""
    for path in ("/api/customers", "/api/customers/", "/api/customers/1"):
        assert client.get(path).status_code in (401, 403, 404), f"{path} đang mở công khai!"


# ---- ĐỐI CHỨNG ÂM -----------------------------------------------------------
# Một test xanh không chứng minh nó KIỂM ĐƯỢC gì. Ba hàm dưới phá đúng thứ mà
# các test trên bảo vệ, và phải XANH (tức là phép đo nhận ra cái sai).
def test_NEGATIVE_control_phone_normalization_is_what_protects_identity(
    db, client, valid_lead_payload
):
    """Chứng minh test `test_phone_formatting_variants_reuse_customer` là phép đo THẬT.

    Chuỗi THÔ khác nhau, nhưng sau chuẩn hoá phải GIỐNG NHAU — chính bước chuẩn hoá
    là thứ làm danh tính hoạt động. Bỏ bước đó đi thì mỗi cách gõ thành một khách.
    """
    from app.phone import normalize_phone as np

    base = "0911000021"
    plus84 = f"+84{base[1:]}"
    spaced = f" {base} "

    # 1. Chuỗi thô THẬT SỰ khác nhau (nếu không, phép đo vô nghĩa)
    assert len({base, plus84, spaced}) == 3
    # 2. Sau chuẩn hoá phải về CÙNG một giá trị — đây là điều đang được bảo vệ
    assert np(base) == np(plus84) == np(spaced) == base

    # 3. Và hệ thống thật gộp chúng vào MỘT khách
    a = client.post(
        "/api/leads", json={**valid_lead_payload, "phone": base, "iphone_model": "iphone-16"}
    )
    b = client.post(
        "/api/leads", json={**valid_lead_payload, "phone": plus84, "iphone_model": "iphone-17"}
    )
    assert a.status_code == 201 and b.status_code == 201, (a.text, b.text)
    assert (
        _customer_of(db, a.json()["gift_code"]).id == _customer_of(db, b.json()["gift_code"]).id
    ), "hai cách gõ cùng một SĐT PHẢI về cùng một khách"


def test_NEGATIVE_control_unique_index_blocks_duplicate_customer(db):
    """UNIQUE ở tầng DB thật sự chặn — không chỉ là lời hứa ở tầng ứng dụng."""
    from sqlalchemy.exc import IntegrityError

    db.add(Customer(full_name="A", phone_normalized="0911000099", status="ACTIVE"))
    db.flush()
    db.add(Customer(full_name="B", phone_normalized="0911000099", status="ACTIVE"))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return
    raise AssertionError("UNIQUE(phone_normalized) KHÔNG chặn được khách trùng!")


def test_NEGATIVE_control_one_primary_device_enforced(db, client, valid_lead_payload):
    """Partial unique index chặn việc có HAI máy chính cùng lúc."""
    from sqlalchemy.exc import IntegrityError

    r = client.post(
        "/api/leads",
        json={**valid_lead_payload, "phone": "0911000022", "iphone_model": "iphone-16"},
    )
    c = _customer_of(db, r.json()["gift_code"])
    db.add(
        CustomerDevice(
            customer_id=c.id, brand="Apple", display_name="X", model_code="x", is_primary=True
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return
    raise AssertionError("Đã tạo được máy chính THỨ HAI — index không chặn!")
