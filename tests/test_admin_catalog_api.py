"""API quản trị danh mục iPhone (G06): thêm/sửa model, validate, và "không sửa HTML".

NGUYÊN TẮC ĐO LƯỜNG: mỗi test an ninh ở đây đã được kiểm bằng **đối chứng âm**
(phá thứ nó bảo vệ → phải FAIL). Kết quả ghi ở `docs/MASTER_STATUS.md` §20.

Riêng yêu cầu "thêm model qua API admin → landing thấy model đó mà KHÔNG đổi file
HTML nào" được đo bằng **hai phép đo độc lập**:

1. API công khai `/api/catalog/iphone-models` (đúng thứ mà landing gọi) trả về model mới.
2. **Băm SHA-256 của mọi file `.html`** trước và sau — phải giống nhau từng byte.
   Băm byte là phép đo, không phải đọc chữ rồi suy ra.

Phép đo thứ ba — trình duyệt thật nạp landing và thấy `<option>` mới — nằm ở
`tests_e2e/test_g04_g06_browser.py` vì nó cần Chromium thật.
"""

from __future__ import annotations

import hashlib

import pytest

from app.models import IphoneModel

pytestmark = pytest.mark.integration

STAFF_HEADERS = {"X-Staff-Key": "staff-key-for-tests-only"}

NEW_MODEL = {
    "model_code": "iphone-99-pro",
    "display_name": "iPhone 99 Pro",
    "year": 2027,
    "sort_order": -5,
    "active": True,
}


def html_fingerprints() -> dict[str, str]:
    """SHA-256 của mọi file `.html` ở gốc repo — dùng làm mốc so sánh byte."""
    from app.config import REPO_ROOT

    result = {}
    for path in sorted(REPO_ROOT.glob("*.html")):
        result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert result, "không tìm thấy file HTML nào để đo"
    return result


# ==========================================================================
# 1. XÁC THỰC
# ==========================================================================


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/admin/iphone-models", NEW_MODEL),
        ("patch", "/api/admin/iphone-models/iphone-16-pro-max", {"active": False}),
        ("get", "/api/admin/iphone-models", None),
    ],
)
def test_model_admin_routes_require_staff_auth(client, method, path, payload):
    kwargs = {"json": payload} if payload is not None else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "STAFF_UNAUTHORIZED"


def test_model_admin_does_not_write_without_auth(client, db):
    """Không có khoá thì KHÔNG được tạo model — kiểm bằng số dòng trong bảng."""
    before = len(db.query(IphoneModel).all())
    response = client.post("/api/admin/iphone-models", json=NEW_MODEL)
    assert response.status_code == 401
    assert len(db.query(IphoneModel).all()) == before


def test_model_admin_fails_closed_when_not_configured(client, monkeypatch):
    from app import security

    monkeypatch.setattr(security.settings, "staff_api_keys", "")
    response = client.post("/api/admin/iphone-models", json=NEW_MODEL, headers=STAFF_HEADERS)
    assert response.status_code == 503


# ==========================================================================
# 2. THÊM MODEL — VÀ "KHÔNG TỰ BỊA"
# ==========================================================================


def test_create_model_returns_exactly_what_admin_sent(client, staff_headers):
    """Hệ thống KHÔNG suy đoán: mọi trường trả về đúng bằng dữ liệu admin nhập."""
    response = client.post("/api/admin/iphone-models", json=NEW_MODEL, headers=staff_headers)
    assert response.status_code == 201, response.text

    body = response.json()
    assert body == NEW_MODEL


def test_create_model_does_not_invent_other_models(client, staff_headers, db):
    """Thêm MỘT model thì danh mục tăng ĐÚNG một dòng, không sinh model kèm."""
    before = db.query(IphoneModel).count()
    client.post("/api/admin/iphone-models", json=NEW_MODEL, headers=staff_headers)
    assert db.query(IphoneModel).count() == before + 1


def test_create_model_appears_in_public_catalog(client, staff_headers):
    client.post("/api/admin/iphone-models", json=NEW_MODEL, headers=staff_headers)

    catalog = client.get("/api/catalog/iphone-models").json()
    codes = [item["model_code"] for item in catalog]
    assert "iphone-99-pro" in codes
    # sort_order = -5 nên đứng đầu — đúng thứ tự landing sẽ hiển thị.
    assert codes[0] == "iphone-99-pro"
    assert set(catalog[0]) == {"year", "model_code", "display_name"}


def test_create_model_does_not_change_any_html_file(client, staff_headers):
    """Yêu cầu cốt lõi của G06: thêm model KHÔNG phải sửa HTML landing.

    Đo bằng BĂM BYTE của mọi file `.html` trước và sau, không đọc chữ rồi suy ra.
    """
    before = html_fingerprints()

    created = client.post("/api/admin/iphone-models", json=NEW_MODEL, headers=staff_headers)
    assert created.status_code == 201

    catalog = client.get("/api/catalog/iphone-models").json()
    assert "iphone-99-pro" in {item["model_code"] for item in catalog}

    after = html_fingerprints()
    assert after == before, "có file HTML bị đổi trong khi thêm model"


def test_create_model_accepts_uppercase_code_and_normalizes_it(client, staff_headers):
    payload = {**NEW_MODEL, "model_code": "IPHONE-99-PRO"}
    response = client.post("/api/admin/iphone-models", json=payload, headers=staff_headers)
    assert response.status_code == 201
    assert response.json()["model_code"] == "iphone-99-pro"


def test_create_model_rejects_duplicate_code(client, staff_headers):
    client.post("/api/admin/iphone-models", json=NEW_MODEL, headers=staff_headers)
    response = client.post("/api/admin/iphone-models", json=NEW_MODEL, headers=staff_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MODEL_CODE_EXISTS"


def test_create_model_rejects_code_already_seeded(client, staff_headers):
    payload = {**NEW_MODEL, "model_code": "iphone-16-pro-max"}
    response = client.post("/api/admin/iphone-models", json=payload, headers=staff_headers)
    assert response.status_code == 409


# ==========================================================================
# 3. VALIDATE `model_code`
# ==========================================================================


@pytest.mark.parametrize(
    "bad_code",
    [
        "-iphone-99",  # bắt đầu bằng gạch ngang
        "iphone 17",  # khoảng trắng
        "iphone_17",  # gạch dưới
        "iphone.17",  # dấu chấm
        "iphone/17",  # dấu gạch chéo
        "a" * 65,  # quá 64 ký tự
        "<script>alert(1)</script>",
        "iphone'17",
        "cập-nhật",
    ],
)
def test_create_model_rejects_invalid_slug(client, staff_headers, bad_code):
    payload = {**NEW_MODEL, "model_code": bad_code}
    response = client.post("/api/admin/iphone-models", json=payload, headers=staff_headers)
    assert response.status_code == 422, f"{bad_code!r} lọt qua: {response.text}"


@pytest.mark.parametrize("good_code", ["i", "a1", "iphone-99", "a" * 64, "0-model", "iphone--ok"])
def test_create_model_accepts_valid_slug(client, staff_headers, good_code):
    payload = {**NEW_MODEL, "model_code": good_code}
    response = client.post("/api/admin/iphone-models", json=payload, headers=staff_headers)
    assert response.status_code == 201, f"{good_code!r} bị từ chối: {response.text}"


# ==========================================================================
# 4. VALIDATE `year`
# ==========================================================================


@pytest.mark.parametrize("bad_year", [2006, 1999, 1, 0, -2024])
def test_create_model_rejects_year_before_2007(client, staff_headers, bad_year):
    """iPhone đời đầu là 2007 — sớm hơn là dữ liệu rác, không phải model."""
    payload = {**NEW_MODEL, "year": bad_year}
    response = client.post("/api/admin/iphone-models", json=payload, headers=staff_headers)
    assert response.status_code == 422, f"năm {bad_year} lọt qua"


def test_create_model_accepts_the_boundary_year(client, staff_headers):
    payload = {**NEW_MODEL, "year": 2007, "model_code": "iphone-original"}
    response = client.post("/api/admin/iphone-models", json=payload, headers=staff_headers)
    assert response.status_code == 201
    assert response.json()["year"] == 2007


@pytest.mark.parametrize("bad_year", [2101, 99999])
def test_create_model_rejects_absurd_year(client, staff_headers, bad_year):
    payload = {**NEW_MODEL, "year": bad_year}
    response = client.post("/api/admin/iphone-models", json=payload, headers=staff_headers)
    assert response.status_code == 422


def test_create_model_rejects_missing_year(client, staff_headers):
    payload = {k: v for k, v in NEW_MODEL.items() if k != "year"}
    response = client.post("/api/admin/iphone-models", json=payload, headers=staff_headers)
    assert response.status_code == 422


def test_create_model_rejects_non_numeric_year(client, staff_headers):
    payload = {**NEW_MODEL, "year": "hai nghìn"}
    response = client.post("/api/admin/iphone-models", json=payload, headers=staff_headers)
    assert response.status_code == 422


# ==========================================================================
# 5. VALIDATE CÁC TRƯỜNG KHÁC
# ==========================================================================


@pytest.mark.parametrize("bad_name", ["", "   ", "Ok\x00Name"])
def test_create_model_rejects_bad_display_name(client, staff_headers, bad_name):
    payload = {**NEW_MODEL, "display_name": bad_name}
    response = client.post("/api/admin/iphone-models", json=payload, headers=staff_headers)
    assert response.status_code == 422, f"{bad_name!r} lọt qua"


def test_create_model_forbids_unknown_fields(client, staff_headers):
    """Client không được gửi trường lạ (ví dụ `id`) — `extra="forbid"`."""
    payload = {**NEW_MODEL, "id": 999}
    response = client.post("/api/admin/iphone-models", json=payload, headers=staff_headers)
    assert response.status_code == 422


def test_create_model_rejects_missing_code(client, staff_headers):
    payload = {k: v for k, v in NEW_MODEL.items() if k != "model_code"}
    response = client.post("/api/admin/iphone-models", json=payload, headers=staff_headers)
    assert response.status_code == 422


# ==========================================================================
# 6. SỬA MODEL
# ==========================================================================


def test_patch_updates_display_name_active_and_sort_order(client, staff_headers):
    response = client.patch(
        "/api/admin/iphone-models/iphone-16-pro-max",
        json={"display_name": "iPhone 16 Pro Max (bản mới)", "active": False, "sort_order": 42},
        headers=staff_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["display_name"] == "iPhone 16 Pro Max (bản mới)"
    assert body["active"] is False
    assert body["sort_order"] == 42
    assert body["model_code"] == "iphone-16-pro-max"


def test_patch_partial_update_leaves_other_fields_alone(client, staff_headers):
    before = client.get("/api/admin/iphone-models", headers=staff_headers).json()
    original = next(m for m in before if m["model_code"] == "iphone-16-pro-max")

    after = client.patch(
        "/api/admin/iphone-models/iphone-16-pro-max",
        json={"sort_order": 7},
        headers=staff_headers,
    ).json()

    assert after["sort_order"] == 7
    assert after["display_name"] == original["display_name"]
    assert after["active"] == original["active"]
    assert after["year"] == original["year"]


def test_patch_deactivating_model_hides_it_from_landing(client, staff_headers):
    client.patch(
        "/api/admin/iphone-models/iphone-16-pro-max",
        json={"active": False},
        headers=staff_headers,
    )

    catalog = client.get("/api/catalog/iphone-models").json()
    assert "iphone-16-pro-max" not in {item["model_code"] for item in catalog}

    # Nhưng khu vực quản trị vẫn thấy, để bật lại được.
    admin_view = client.get("/api/admin/iphone-models", headers=staff_headers).json()
    assert "iphone-16-pro-max" in {item["model_code"] for item in admin_view}


def test_patch_unknown_model_returns_404(client, staff_headers):
    response = client.patch(
        "/api/admin/iphone-models/iphone-khong-ton-tai",
        json={"active": False},
        headers=staff_headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"


def test_patch_empty_body_is_rejected(client, staff_headers):
    response = client.patch(
        "/api/admin/iphone-models/iphone-16-pro-max", json={}, headers=staff_headers
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        # Chỉ có trường lạ: bị chặn — nhưng chặn bởi "thiếu trường hợp lệ", không
        # phải bởi `extra="forbid"`. Một mình ca này KHÔNG đo được điều cần đo.
        {"model_code": "iphone-khac", "year": 1999},
        # Có trường hợp lệ ĐI KÈM trường lạ: đây mới là ca đo `extra="forbid"`.
        # Với `extra="ignore"` thì API trả 200 và lặng lẽ bỏ qua `model_code` —
        # người gọi tưởng đã đổi được mã trong khi thực tế không.
        {"active": False, "model_code": "iphone-khac"},
        {"sort_order": 3, "year": 1999},
        {"display_name": "Tên mới", "model_code": "iphone-khac"},
    ],
)
def test_patch_cannot_change_model_code_or_year(client, staff_headers, payload):
    """Đổi `model_code`/`year` phải bị TỪ CHỐI (422), không im lặng bỏ qua.

    Đối chứng âm (đã chạy, MASTER_STATUS §20): đổi `extra="forbid"` thành
    `extra="ignore"` → các ca TRỘN trường hợp lệ + trường lạ FAIL. Bản đầu của
    test này chỉ có ca "toàn trường lạ" và **không FAIL** — nó đạt được nhờ một
    validator khác, tức là nó chưa hề kiểm `extra="forbid"`.
    """
    response = client.patch(
        "/api/admin/iphone-models/iphone-16-pro-max",
        json=payload,
        headers=staff_headers,
    )
    assert response.status_code == 422, f"{payload} lọt qua: {response.text}"


def test_patch_does_not_change_any_html_file(client, staff_headers):
    before = html_fingerprints()
    client.patch(
        "/api/admin/iphone-models/iphone-16-pro-max",
        json={"display_name": "iPhone 16 Pro Max mới"},
        headers=staff_headers,
    )
    assert html_fingerprints() == before
    assert "iPhone 16 Pro Max mới" in {
        item["display_name"] for item in client.get("/api/catalog/iphone-models").json()
    }


# ==========================================================================
# 7. LEADS DÙNG MODEL MỚI
# ==========================================================================


def test_lead_can_be_created_with_a_model_added_via_admin(
    client, staff_headers, valid_lead_payload
):
    """Model thêm qua admin phải dùng được ngay ở luồng thu lead (không chỉ hiển thị)."""
    client.post(
        "/api/admin/iphone-models",
        json={**NEW_MODEL, "model_code": "iphone-99-pro", "display_name": "iPhone 99 Pro"},
        headers=staff_headers,
    )

    response = client.post(
        "/api/leads", json={**valid_lead_payload, "iphone_model": "iphone-99-pro"}
    )
    assert response.status_code == 201, response.text

    detail = client.get(
        f"/api/admin/leads/{response.json()['lead_id']}", headers=staff_headers
    ).json()
    assert detail["iphone_model"] == "iPhone 99 Pro"
    assert detail["iphone_year"] == NEW_MODEL["year"]


def test_inactive_model_cannot_be_used_for_a_lead(client, staff_headers, valid_lead_payload):
    client.post(
        "/api/admin/iphone-models",
        json={**NEW_MODEL, "model_code": "iphone-99-pro", "active": False},
        headers=staff_headers,
    )
    response = client.post(
        "/api/leads", json={**valid_lead_payload, "iphone_model": "iphone-99-pro"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MODEL_NOT_IN_CATALOG"
