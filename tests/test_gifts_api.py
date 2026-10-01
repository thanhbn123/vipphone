"""API gift: tra cứu cho nhân viên, che PII, và QR CHUẨN (giải mã thật).

Kịch bản 6 (tra cứu gift) và 10 (mã không hợp lệ).
"""

from __future__ import annotations

import io

import pytest
import zxingcpp
from PIL import Image
from sqlalchemy import select

from app.models import IphoneModel, Lead

pytestmark = pytest.mark.integration


def create_lead(client, payload) -> dict:
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------- 6. tra cứu gift
def test_lookup_requires_staff_auth(client, valid_lead_payload):
    created = create_lead(client, valid_lead_payload)
    response = client.get(f"/api/gifts/{created['gift_code']}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "STAFF_UNAUTHORIZED"


def test_lookup_fails_closed_when_staff_auth_not_configured(
    client, valid_lead_payload, monkeypatch
):
    """Chưa cấu hình xác thực thì ĐÓNG route (503), tuyệt đối không mở toang."""
    from app import security

    created = create_lead(client, valid_lead_payload)
    monkeypatch.setattr(security.settings, "staff_api_keys", "")

    response = client.get(f"/api/gifts/{created['gift_code']}")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STAFF_AUTH_NOT_CONFIGURED"


def test_lookup_rejects_wrong_key(client, valid_lead_payload):
    created = create_lead(client, valid_lead_payload)
    response = client.get(f"/api/gifts/{created['gift_code']}", headers={"X-Staff-Key": "sai-khoa"})
    assert response.status_code == 401


def test_lookup_accepts_bearer_token(client, valid_lead_payload, staff_headers):
    from tests.conftest import STAFF_KEY

    created = create_lead(client, valid_lead_payload)
    response = client.get(
        f"/api/gifts/{created['gift_code']}",
        headers={"Authorization": f"Bearer {STAFF_KEY}"},
    )
    assert response.status_code == 200


def test_lookup_returns_minimum_fields(client, valid_lead_payload, staff_headers):
    created = create_lead(client, valid_lead_payload)
    response = client.get(f"/api/gifts/{created['gift_code']}", headers=staff_headers)

    assert response.status_code == 200
    body = response.json()

    assert body["gift_code"] == created["gift_code"]
    assert body["lead_id"] == created["lead_id"]
    assert body["full_name"] == "Nguyễn Văn A"
    assert body["iphone_model"] == "iPhone 16 Pro Max"
    assert body["iphone_year"] == 2024
    assert body["case_color"] == "Đen"
    assert body["gift_status"] == "NEW"
    assert body["redeemed_at"] is None


def test_lookup_minimizes_pii(client, valid_lead_payload, staff_headers):
    """KHÔNG được trả số điện thoại đầy đủ và không trả trường tracking."""
    created = create_lead(client, valid_lead_payload)
    body = client.get(f"/api/gifts/{created['gift_code']}", headers=staff_headers).json()

    assert "phone" not in body
    assert body["phone_masked"] == "0912***678"
    assert "0912345678" not in str(body)

    for field in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "ref", "source"):
        assert field not in body

    assert "company_name" not in body
    assert "bni_chapter" not in body
    assert "referrer_name" not in body


def test_lookup_is_case_insensitive(client, valid_lead_payload, staff_headers):
    created = create_lead(client, valid_lead_payload)
    lower = created["gift_code"].lower()
    response = client.get(f"/api/gifts/{lower}", headers=staff_headers)
    assert response.status_code == 200
    assert response.json()["gift_code"] == created["gift_code"]


def test_lookup_trims_whitespace(client, valid_lead_payload, staff_headers):
    created = create_lead(client, valid_lead_payload)
    response = client.get(f"/api/gifts/%20{created['gift_code']}%20", headers=staff_headers)
    assert response.status_code == 200


# ------------------------------------------------------------ 10. mã không hợp lệ
@pytest.mark.parametrize(
    "bad_code",
    ["VIP-26-ABC", "VIP-26-ABCDEFG", "KHONG-PHAI-MA", "VIP-2-ABCDEF", "123", "VIP-26-!!!!!!"],
)
def test_malformed_gift_code_returns_404(client, staff_headers, bad_code):
    response = client.get(f"/api/gifts/{bad_code}", headers=staff_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GIFT_NOT_FOUND"


def test_unknown_but_wellformed_code_returns_404(client, staff_headers):
    response = client.get("/api/gifts/VIP-26-ZZZZZZ", headers=staff_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GIFT_NOT_FOUND"


def test_lookup_does_not_leak_existence_without_auth(client, staff_headers):
    """Không có quyền thì phải 401 cho MỌI mã, kể cả mã không tồn tại."""
    for code in ("VIP-26-ZZZZZZ", "VIP-26-ABCDEF"):
        assert client.get(f"/api/gifts/{code}").status_code == 401


# ------------------------------------------------------------------- QR chuẩn
def decode_qr(png_bytes: bytes) -> list[str]:
    """Giải mã QR thật bằng zxing-cpp (bộ giải mã tham chiếu).

    ⚠️  GHI CHÚ ĐO LƯỜNG — đã đo, không suy đoán:
    Ban đầu bộ test dùng `cv2.QRCodeDetector` của OpenCV. Nó GIẢI MÃ ĐƯỢC
    hầu hết gift code nhưng THẤT BẠI với một số nội dung, ví dụ
    `VIP-26-AAAAAA` và `VIP-26-BBBBBB` (chuỗi ký tự lặp dài) — cùng lúc đó
    zxing-cpp giải mã bình thường. Vì gift code là chuỗi ngẫu nhiên nên hoàn
    toàn có thể rơi vào ca đó.

    Kết luận: OpenCV KHÔNG đủ tin cậy để làm thứ kiểm chứng QR. Dùng zxing-cpp.
    Đây là dạng lỗi "phép đo thiếu một ca" — công cụ kiểm chứng tự nó không
    trung thực ở một số đầu vào.
    """
    image = Image.open(io.BytesIO(png_bytes))
    result = zxingcpp.read_barcode(image)
    assert result is not None, "Không tìm thấy mã QR trong ảnh"
    assert result.format == zxingcpp.BarcodeFormat.QRCode, result.format
    return [line for line in result.text.splitlines() if line]


def test_qr_endpoint_returns_png(client, valid_lead_payload):
    created = create_lead(client, valid_lead_payload)
    response = client.get(f"/api/gifts/{created['gift_code']}/qr.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_qr_decodes_to_public_redeem_url(client, valid_lead_payload):
    """Nội dung QR phải giải mã ra ĐÚNG URL công khai."""
    created = create_lead(client, valid_lead_payload)
    png = client.get(f"/api/gifts/{created['gift_code']}/qr.png").content

    decoded = decode_qr(png)
    assert decoded == [f"http://testserver/redeem?code={created['gift_code']}"]


def test_qr_contains_no_pii(client, valid_lead_payload):
    """QR TUYỆT ĐỐI không được chứa tên, số điện thoại, công ty hay PII khác."""
    created = create_lead(client, valid_lead_payload)
    png = client.get(f"/api/gifts/{created['gift_code']}/qr.png").content

    payload = "\n".join(decode_qr(png))

    assert "Nguyễn Văn A" not in payload
    assert "0912345678" not in payload
    assert "Công ty TNHH ABC" not in payload
    assert "BNI Growth" not in payload
    assert "Trần Thị B" not in payload
    # Chỉ được có đúng URL công khai.
    assert payload == f"http://testserver/redeem?code={created['gift_code']}"


def test_qr_decoder_can_tell_payloads_apart():
    """Đối chứng: bộ giải mã PHẢI phân biệt được hai nội dung khác nhau.

    Nếu không, phép đo ở trên vô nghĩa (nó sẽ luôn báo "đúng").
    """
    from app.services.gifts import render_qr_png

    a = render_qr_png("http://testserver/redeem?code=VIP-26-AAAAAA")
    b = render_qr_png("http://testserver/redeem?code=VIP-26-BBBBBB")

    assert decode_qr(a) == ["http://testserver/redeem?code=VIP-26-AAAAAA"]
    assert decode_qr(b) == ["http://testserver/redeem?code=VIP-26-BBBBBB"]
    assert a != b


def test_qr_not_available_for_malformed_code(client):
    assert client.get("/api/gifts/khong-phai-ma/qr.png").status_code == 404


def test_qr_not_available_for_unknown_code(client):
    assert client.get("/api/gifts/VIP-26-ZZZZZZ/qr.png").status_code == 404


def test_qr_has_no_store_cache_header(client, valid_lead_payload):
    created = create_lead(client, valid_lead_payload)
    response = client.get(f"/api/gifts/{created['gift_code']}/qr.png")
    assert response.headers["cache-control"] == "no-store"


# ------------------------------------------------------------------ danh mục
def test_catalog_lists_only_active_models(client, db):
    db.execute(
        __import__("sqlalchemy").text(
            "UPDATE iphone_models SET active = false WHERE model_code = 'iphone-xr'"
        )
    )
    db.commit()

    response = client.get("/api/catalog/iphone-models")
    assert response.status_code == 200
    body = response.json()

    codes = {item["model_code"] for item in body}
    assert len(body) == 27
    assert "iphone-xr" not in codes
    assert "iphone-16-pro-max" in codes
    # Model mới nhất đứng trước (sort_order nhỏ hơn).
    assert body[0]["model_code"].startswith("iphone-16")


def test_catalog_item_shape(client):
    body = client.get("/api/catalog/iphone-models").json()
    assert set(body[0]) == {"year", "model_code", "display_name"}


def test_new_catalog_model_available_without_html_change(client, db):
    """G06: thêm model mới vào danh mục mà KHÔNG phải sửa HTML landing."""
    db.add(
        IphoneModel(
            year=2025,
            model_code="iphone-17",
            display_name="iPhone 17",
            active=True,
            sort_order=-1,
        )
    )
    db.commit()

    body = client.get("/api/catalog/iphone-models").json()
    assert body[0]["model_code"] == "iphone-17"

    # Và lead dùng model mới đó phải tạo được.
    response = client.post(
        "/api/leads",
        json={
            "full_name": "Khách Mới",
            "phone": "0911111111",
            "iphone_model": "iphone-17",
            "case_color": "Xanh",
            "consent": True,
        },
    )
    assert response.status_code == 201, response.text


def test_catalog_model_matches_seeded_database(db):
    assert db.execute(select(Lead)).first() is None
    assert len(db.execute(select(IphoneModel)).scalars().all()) == 28
