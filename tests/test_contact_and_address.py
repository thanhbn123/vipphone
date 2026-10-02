"""Gmail + địa chỉ giao hàng (UI-2).

Bối cảnh: anh cần 2 nhóm dữ liệu này để **tự động lên đơn với phần mềm vận chuyển**
(Viettel Post). API của hãng nhận PROVINCE / DISTRICT / WARD / ADDRESS RIÊNG, nên địa
chỉ được lưu tách sẵn 4 phần — gom một chuỗi thì lúc lên đơn vẫn phải tách tay.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.models import Lead

pytestmark = pytest.mark.integration

FULL_ADDRESS = {
    "email": "Khach.Hang@Gmail.COM",
    "address": "12 Nguyễn Huệ, Phường Bến Nghé, Quận 1, TP. Hồ Chí Minh",
}


def create(client, payload, **overrides):
    body = {**payload, **overrides}
    return client.post("/api/leads", json=body)


def test_full_contact_and_address_are_saved(client, valid_lead_payload, db):
    response = create(client, valid_lead_payload, **FULL_ADDRESS)
    assert response.status_code == 201, response.text

    lead = db.execute(select(Lead).order_by(Lead.id.desc())).scalars().first()
    # Gmail được CHUẨN HOÁ: bỏ khoảng trắng và hạ chữ thường.
    assert lead.email == "khach.hang@gmail.com"
    assert lead.address == "12 Nguyễn Huệ, Phường Bến Nghé, Quận 1, TP. Hồ Chí Minh"


def test_contact_and_address_are_optional(client, valid_lead_payload, db):
    """KHÔNG bắt buộc — bắt buộc sẽ làm rớt khách đang đứng ở quầy."""
    response = create(client, valid_lead_payload)
    assert response.status_code == 201, response.text

    lead = db.execute(select(Lead).order_by(Lead.id.desc())).scalars().first()
    for field in ("email", "address"):
        assert getattr(lead, field) is None, f"{field} phải là NULL, không phải chuỗi rỗng"


def test_blank_strings_become_null_not_empty_string(client, valid_lead_payload, db):
    """Ô để trống gửi lên chuỗi rỗng ⇒ phải lưu NULL, không lưu ''."""
    response = create(
        client,
        valid_lead_payload,
        email="   ",
        address="   ",
    )
    assert response.status_code == 201, response.text
    lead = db.execute(select(Lead).order_by(Lead.id.desc())).scalars().first()
    assert lead.email is None
    assert lead.address is None


@pytest.mark.parametrize("bad", ["khong-phai-email", "a@b", "a b@c.com", "@gmail.com", "a@@b.com"])
def test_invalid_email_is_rejected(client, valid_lead_payload, bad):
    response = create(client, valid_lead_payload, email=bad)
    assert response.status_code == 422, f"{bad!r} phải bị từ chối, nhận {response.status_code}"


@pytest.mark.parametrize(
    ("field", "length"),
    [
        ("email", 255),
        ("address", 301),
    ],
)
def test_overlong_values_are_rejected(client, valid_lead_payload, field, length):
    response = create(client, valid_lead_payload, **{field: "x" * length})
    assert response.status_code == 422


def test_admin_detail_returns_contact_and_address(client, valid_lead_payload, staff_headers):
    created = create(client, valid_lead_payload, **FULL_ADDRESS).json()
    body = client.get(f"/api/admin/leads/{created['lead_id']}", headers=staff_headers).json()
    assert body["email"] == "khach.hang@gmail.com"
    assert "Nguyễn Huệ" in body["address"]


def test_csv_has_the_new_columns(client, valid_lead_payload, staff_headers):
    from app.services.admin_leads import CSV_COLUMNS

    create(client, valid_lead_payload, **FULL_ADDRESS)
    response = client.get("/api/admin/leads.csv", headers=staff_headers)
    header = response.text.lstrip("\ufeff").splitlines()[0]

    for column in ("email", "address"):
        assert column in CSV_COLUMNS, f"CSV_COLUMNS thiếu {column}"
        assert column in header, f"header CSV thiếu {column}"
    assert "khach.hang@gmail.com" in response.text


def test_audit_metadata_never_carries_email_or_address(client, valid_lead_payload, db):
    """Audit là vết kiểm toán, KHÔNG phải bản sao dữ liệu khách."""
    create(client, valid_lead_payload, **FULL_ADDRESS)
    rows = db.execute(text("SELECT metadata::text FROM audit_events")).scalars().all()
    blob = " ".join(rows)

    for secret in ("khach.hang@gmail.com", "Nguyễn Huệ", "Bến Nghé", "TP. Hồ Chí Minh"):
        assert secret not in blob, f"audit rò PII: {secret}"


def test_staff_lookup_does_not_return_address(client, valid_lead_payload, staff_headers):
    """Tra cứu tại quầy chỉ trả thứ cần để phát quà — không trả địa chỉ/Gmail."""
    created = create(client, valid_lead_payload, **FULL_ADDRESS).json()
    body = client.get(f"/api/gifts/{created['gift_code']}", headers=staff_headers).json()

    for field in ("email", "address"):
        assert field not in body, f"tra cứu tại quầy KHÔNG được trả {field}"


# ============================================================================
# UI-4 — "Màu ốp mong muốn" từ Ô CHỌN thành Ô GHI CHÚ tự do, KHÔNG bắt buộc
# ============================================================================
def test_lead_without_case_color_is_accepted(client, valid_lead_payload, db):
    """Không bắt buộc nữa: khách bỏ trống vẫn nhận được quà."""
    payload = {k: v for k, v in valid_lead_payload.items() if k != "case_color"}
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 201, response.text

    lead = db.execute(select(Lead).order_by(Lead.id.desc())).scalars().first()
    assert lead.case_color is None, "ô để trống phải lưu NULL, không lưu chuỗi rỗng"


def test_case_color_accepts_free_text_not_just_the_old_list(client, valid_lead_payload, db):
    """Đây là lý do phải đổi: ô chọn cũ chỉ nhận 6 giá trị cố định.

    Khách ghi 'Xanh rêu' hoặc 'Hồng pastel' — thứ KHÔNG có trong danh sách cũ —
    vẫn phải lưu được.
    """
    response = create(client, valid_lead_payload, case_color="Xanh rêu")
    assert response.status_code == 201, response.text
    lead = db.execute(select(Lead).order_by(Lead.id.desc())).scalars().first()
    assert lead.case_color == "Xanh rêu"


def test_overlong_case_color_is_rejected(client, valid_lead_payload):
    assert create(client, valid_lead_payload, case_color="x" * 41).status_code == 422


def test_lookup_and_admin_tolerate_missing_case_color(client, valid_lead_payload, staff_headers):
    """Mọi chỗ ĐỌC `case_color` phải chịu được None, nếu không sẽ 500."""
    payload = {k: v for k, v in valid_lead_payload.items() if k != "case_color"}
    created = client.post("/api/leads", json=payload).json()

    lookup = client.get(f"/api/gifts/{created['gift_code']}", headers=staff_headers)
    assert lookup.status_code == 200, lookup.text
    assert lookup.json()["case_color"] is None

    detail = client.get(f"/api/admin/leads/{created['lead_id']}", headers=staff_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["case_color"] is None


def test_redeem_works_without_case_color(client, valid_lead_payload, staff_headers):
    """Đường PHÁT QUÀ cũng đọc case_color — phải không sập khi rỗng."""
    payload = {k: v for k, v in valid_lead_payload.items() if k != "case_color"}
    created = client.post("/api/leads", json=payload).json()

    response = client.post(
        f"/api/gifts/{created['gift_code']}/redeem", json={}, headers=staff_headers
    )
    assert response.status_code == 200, response.text
    # LƯU Ý: response PHÁT QUÀ không có trường case_color (xem GiftRedeemResponse) —
    # điều cần chứng minh chỉ là đường ghi này không sập khi case_color rỗng.
    assert response.json()["gift_status"] == "REDEEMED"


def test_csv_exports_empty_case_color_without_crashing(client, valid_lead_payload, staff_headers):
    payload = {k: v for k, v in valid_lead_payload.items() if k != "case_color"}
    client.post("/api/leads", json=payload)
    response = client.get("/api/admin/leads.csv", headers=staff_headers)
    assert response.status_code == 200
    assert "case_color" in response.text.splitlines()[0]
