"""API thu lead — các kịch bản bắt buộc 1, 2, 3, 4, 5, 11, 12."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text

from app.models import AuditEvent, Lead

pytestmark = pytest.mark.integration


def count_leads(db) -> int:
    return db.execute(select(func.count()).select_from(Lead)).scalar_one()


# ---------------------------------------------------------------- 1. lead hợp lệ
def test_valid_lead_is_created(client, db, valid_lead_payload):
    response = client.post("/api/leads", json=valid_lead_payload)

    assert response.status_code == 201, response.text
    body = response.json()

    assert body["gift_status"] == "NEW"
    assert body["duplicate"] is False
    assert body["gift_code"].startswith("VIP-")
    assert len(body["gift_code"]) == len("VIP-26-XXXXXX")
    # lead_id phải là UUID hợp lệ
    import uuid

    uuid.UUID(body["lead_id"])

    lead = db.execute(select(Lead)).scalar_one()
    assert lead.phone == "0912345678"
    assert lead.gift_code == body["gift_code"]
    assert lead.consent is True
    assert lead.gift_status == "NEW"
    assert lead.redeemed_at is None
    assert lead.case_color == "Đen"
    # Năm và tên máy lấy từ DANH MỤC, không lấy từ client.
    assert lead.iphone_model == "iPhone 16 Pro Max"
    assert lead.iphone_year == 2024


def test_lead_creation_writes_audit_events(client, db, valid_lead_payload):
    client.post("/api/leads", json=valid_lead_payload)

    events = db.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars().all()
    types = [event.event_type for event in events]

    assert types == ["LEAD_CREATED", "GIFT_CREATED"]
    for event in events:
        assert event.actor.startswith("public:")
        assert event.gift_code is not None
        # Audit TUYỆT ĐỐI không chứa PII.
        assert not (event.event_metadata or {}).keys() & {
            "phone",
            "full_name",
            "company_name",
        }


def test_audit_metadata_drops_forbidden_keys(db, valid_lead_payload):
    from app.audit import scrub_metadata

    cleaned = scrub_metadata(
        {"model_code": "iphone-16", "phone": "0912345678", "full_name": "A", "la": 1}
    )
    assert cleaned == {"model_code": "iphone-16"}


# ------------------------------------------------------------ 2. SĐT không hợp lệ
@pytest.mark.parametrize(
    "bad_phone",
    ["12345", "091234567", "09123456789", "0212345678", "khong-phai-so", ""],
)
def test_invalid_phone_is_rejected(client, db, valid_lead_payload, bad_phone):
    payload = {**valid_lead_payload, "phone": bad_phone}
    response = client.post("/api/leads", json=payload)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert "phone" in body["error"]["fields"]
    assert count_leads(db) == 0


def test_phone_is_normalized_before_storage(client, db, valid_lead_payload):
    payload = {**valid_lead_payload, "phone": "+84 912 345 678"}
    response = client.post("/api/leads", json=payload)

    assert response.status_code == 201
    assert db.execute(select(Lead.phone)).scalar_one() == "0912345678"


# ----------------------------------------------------------------- 3. thiếu consent
@pytest.mark.parametrize("consent", [False, None])
def test_missing_consent_is_rejected(client, db, valid_lead_payload, consent):
    payload = {**valid_lead_payload, "consent": consent}
    response = client.post("/api/leads", json=payload)

    assert response.status_code == 422, response.text
    assert "consent" in response.json()["error"]["fields"]
    assert count_leads(db) == 0


def test_consent_field_is_required(client, db, valid_lead_payload):
    payload = dict(valid_lead_payload)
    payload.pop("consent")
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 422
    assert count_leads(db) == 0


# ------------------------------------------------------------- 4. gửi trùng nhiều lần
def test_duplicate_submission_returns_existing_gift(client, db, valid_lead_payload):
    first = client.post("/api/leads", json=valid_lead_payload)
    assert first.status_code == 201
    assert first.json()["duplicate"] is False

    # Gửi lại y hệt (ví dụ khách bấm gửi hai lần, hoặc tải lại trang).
    second = client.post("/api/leads", json=valid_lead_payload)
    assert second.status_code == 201
    body = second.json()

    assert body["duplicate"] is True
    assert body["gift_code"] == first.json()["gift_code"]
    assert body["lead_id"] == first.json()["lead_id"]
    assert count_leads(db) == 1, "KHÔNG được tạo lead thứ hai"


def test_duplicate_policy_normalizes_phone(client, db, valid_lead_payload):
    """Cùng khách viết SĐT kiểu khác vẫn phải nhận CÙNG gift code."""
    first = client.post("/api/leads", json=valid_lead_payload)
    second = client.post("/api/leads", json={**valid_lead_payload, "phone": "+84 912 345 678"})

    assert second.status_code == 201
    assert second.json()["duplicate"] is True
    assert second.json()["gift_code"] == first.json()["gift_code"]
    assert count_leads(db) == 1


def test_different_model_creates_new_gift(client, db, valid_lead_payload):
    """Khác dòng máy thì là gift khác — đúng chính sách."""
    first = client.post("/api/leads", json=valid_lead_payload)
    second = client.post("/api/leads", json={**valid_lead_payload, "iphone_model": "iphone-15"})

    assert second.status_code == 201
    assert second.json()["duplicate"] is False
    assert second.json()["gift_code"] != first.json()["gift_code"]
    assert count_leads(db) == 2


def test_different_phone_creates_new_gift(client, db, valid_lead_payload):
    first = client.post("/api/leads", json=valid_lead_payload)
    second = client.post("/api/leads", json={**valid_lead_payload, "phone": "0987654321"})

    assert second.json()["gift_code"] != first.json()["gift_code"]
    assert count_leads(db) == 2


def test_cancelled_gift_does_not_block_new_gift(client, db, valid_lead_payload):
    """Gift đã HUỶ thì không chặn việc cấp gift mới."""
    first = client.post("/api/leads", json=valid_lead_payload)
    db.execute(
        text("UPDATE leads SET gift_status = 'CANCELLED' WHERE gift_code = :code"),
        {"code": first.json()["gift_code"]},
    )
    db.commit()

    second = client.post("/api/leads", json=valid_lead_payload)
    assert second.status_code == 201
    assert second.json()["duplicate"] is False
    assert second.json()["gift_code"] != first.json()["gift_code"]


# ------------------------------------------------------------ 5. gift code duy nhất
def test_gift_codes_are_unique_across_leads(client, db, valid_lead_payload):
    codes = set()
    for index in range(15):
        payload = {
            **valid_lead_payload,
            "phone": f"09{index:08d}",
        }
        response = client.post("/api/leads", json=payload)
        assert response.status_code == 201, response.text
        codes.add(response.json()["gift_code"])

    assert len(codes) == 15
    assert db.execute(select(func.count(func.distinct(Lead.gift_code)))).scalar_one() == 15


def test_gift_code_collision_is_retried(client, db, valid_lead_payload, monkeypatch):
    """Đụng độ gift code phải THỬ LẠI, không báo lỗi cho khách."""
    from app.services import leads as leads_service

    real_generate = leads_service.generate_gift_code
    first_code = real_generate()
    sequence = iter([first_code, first_code, real_generate()])

    monkeypatch.setattr(
        leads_service, "generate_gift_code", lambda: next(sequence, real_generate())
    )

    first = client.post("/api/leads", json=valid_lead_payload)
    assert first.status_code == 201
    assert first.json()["gift_code"] == first_code

    second = client.post("/api/leads", json={**valid_lead_payload, "phone": "0987654321"})
    assert second.status_code == 201, second.text
    assert second.json()["gift_code"] != first_code


# --------------------------------------------------------- 11. ghi nhận UTM
def test_utm_and_source_are_captured(client, db, valid_lead_payload):
    payload = {
        **valid_lead_payload,
        "source": "facebook",
        "campaign": "camp-10",
        "utm_source": "facebook",
        "utm_medium": "social",
        "utm_campaign": "camp-10",
        "utm_content": "video-a",
        "ref": "MEMBER-42",
    }
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 201, response.text

    lead = db.execute(select(Lead)).scalar_one()
    assert lead.source == "facebook"
    assert lead.campaign == "camp-10"
    assert lead.utm_source == "facebook"
    assert lead.utm_medium == "social"
    assert lead.utm_campaign == "camp-10"
    assert lead.utm_content == "video-a"
    assert lead.ref == "MEMBER-42"


def test_utm_values_are_optional(client, db, valid_lead_payload):
    response = client.post("/api/leads", json=valid_lead_payload)
    assert response.status_code == 201
    lead = db.execute(select(Lead)).scalar_one()
    assert lead.utm_source is None
    assert lead.ref == "BNI123"


@pytest.mark.parametrize(
    "bad_value",
    ["co dau cach", "<script>alert(1)</script>", "a" * 200, "dấu'nháy", "x;DROP TABLE"],
)
def test_unsafe_tracking_values_are_rejected(client, db, valid_lead_payload, bad_value):
    payload = {**valid_lead_payload, "utm_source": bad_value}
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 422, response.text
    assert count_leads(db) == 0


# ---------------------------------------------------------- 12. kiểm tra model
def test_unknown_model_is_rejected(client, db, valid_lead_payload):
    payload = {**valid_lead_payload, "iphone_model": "iphone-99-tu-bia"}
    response = client.post("/api/leads", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MODEL_NOT_IN_CATALOG"
    assert count_leads(db) == 0


def test_inactive_model_is_rejected(client, db, valid_lead_payload):
    db.execute(
        text("UPDATE iphone_models SET active = false WHERE model_code = 'iphone-16-pro-max'")
    )
    db.commit()

    response = client.post("/api/leads", json=valid_lead_payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MODEL_NOT_IN_CATALOG"


def test_client_cannot_supply_year_or_status(client, db, valid_lead_payload):
    """Không tin dữ liệu client: các trường hệ thống phải bị từ chối."""
    for extra in ({"iphone_year": 1999}, {"gift_status": "REDEEMED"}, {"lead_id": "x"}):
        response = client.post("/api/leads", json={**valid_lead_payload, **extra})
        assert response.status_code == 422, f"{extra} phải bị từ chối"

    assert count_leads(db) == 0


def test_model_code_is_case_insensitive(client, db, valid_lead_payload):
    payload = {**valid_lead_payload, "iphone_model": "IPHONE-16-PRO-MAX"}
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 201
    assert db.execute(select(Lead.iphone_model)).scalar_one() == "iPhone 16 Pro Max"


# ------------------------------------------------------- đầu vào dị dạng / bảo mật
@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        "chuoi",
        {"full_name": "A"},
        {
            "full_name": "",
            "phone": "0912345678",
            "iphone_model": "iphone-16",
            "case_color": "Đen",
            "consent": True,
        },
    ],
)
def test_malformed_bodies_are_rejected(client, db, payload):
    response = client.post("/api/leads", json=payload)
    assert response.status_code in (400, 422), response.text
    assert count_leads(db) == 0


def test_oversized_names_are_rejected(client, db, valid_lead_payload):
    response = client.post("/api/leads", json={**valid_lead_payload, "full_name": "A" * 200})
    assert response.status_code == 422
    assert "full_name" in response.json()["error"]["fields"]


def test_error_body_does_not_echo_submitted_pii(client, valid_lead_payload):
    payload = {**valid_lead_payload, "full_name": "Tên Bí Mật XYZ", "phone": "12345"}
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 422
    assert "Tên Bí Mật XYZ" not in response.text


def test_sql_injection_attempt_is_stored_as_literal(client, db, valid_lead_payload):
    payload = {**valid_lead_payload, "full_name": "Robert'); DROP TABLE leads;--"}
    response = client.post("/api/leads", json=payload)

    assert response.status_code == 201
    lead = db.execute(select(Lead)).scalar_one()
    assert lead.full_name == "Robert'); DROP TABLE leads;--"
    # Bảng vẫn còn nguyên.
    assert count_leads(db) == 1


# ------------------------------------------------------------------ rate limit
def test_rate_limit_blocks_after_threshold(client, valid_lead_payload, monkeypatch):
    from app import security

    monkeypatch.setattr(security.lead_rate_limiter, "limit", 3)
    security.lead_rate_limiter.reset()

    statuses = []
    for index in range(5):
        payload = {**valid_lead_payload, "phone": f"09{index:08d}"}
        statuses.append(client.post("/api/leads", json=payload).status_code)

    assert statuses[:3] == [201, 201, 201]
    assert statuses[3] == 429
    assert statuses[4] == 429

    limited = client.post("/api/leads", json={**valid_lead_payload, "phone": "0900000009"})
    assert limited.status_code == 429
    assert limited.headers["Retry-After"].isdigit()
    assert limited.json()["error"]["code"] == "RATE_LIMITED"

    security.lead_rate_limiter.reset()


def test_rate_limit_can_be_disabled(client, valid_lead_payload, monkeypatch):
    from app import security

    monkeypatch.setattr(security.lead_rate_limiter, "limit", 1)
    monkeypatch.setattr(security.settings, "rate_limit_enabled", False)
    security.lead_rate_limiter.reset()

    for index in range(3):
        payload = {**valid_lead_payload, "phone": f"09{index:08d}"}
        assert client.post("/api/leads", json=payload).status_code == 201

    security.lead_rate_limiter.reset()


def test_forwarded_for_is_ignored_by_default(client, valid_lead_payload, monkeypatch):
    """Không tin `X-Forwarded-For` khi chưa bật TRUST_PROXY_HEADERS."""
    from app import security

    assert security.settings.trust_proxy_headers is False
    monkeypatch.setattr(security.lead_rate_limiter, "limit", 1)
    security.lead_rate_limiter.reset()

    first = client.post(
        "/api/leads",
        json={**valid_lead_payload, "phone": "0900000001"},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    second = client.post(
        "/api/leads",
        json={**valid_lead_payload, "phone": "0900000002"},
        headers={"X-Forwarded-For": "5.6.7.8"},
    )

    assert first.status_code == 201
    assert second.status_code == 429, "đổi XFF không được né rate limit"

    security.lead_rate_limiter.reset()
