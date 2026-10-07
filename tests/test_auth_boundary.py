"""Ranh giới xác thực — kiểm BẰNG CÁCH LIỆT KÊ, không bằng danh sách viết tay.

VÌ SAO VIẾT KIỂU NÀY: các test theo từng endpoint chỉ kiểm những route mà người
viết đã NHỚ. Thêm một route admin mới mà quên gắn `require_staff` thì không test
nào đỏ. Test này đi qua **toàn bộ route của app**, nên route mới **tự động** bị kiểm.

Đây là chốt chặn cho tình huống: *public internet → admin mở → redeem mutation mở*.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.main import create_app

pytestmark = pytest.mark.integration

#: Route CÔNG KHAI có chủ đích. Mọi route /api KHÁC đều phải cần xác thực.
#: Thêm một dòng vào đây là một quyết định có ý thức — đó chính là mục đích.
PUBLIC_API_ROUTES = {
    ("GET", "/api/health"),
    ("GET", "/api/ready"),
    ("GET", "/api/public-config"),
    ("GET", "/api/catalog/iphone-models"),
    ("POST", "/api/leads"),
    ("GET", "/api/gifts/{gift_code}/qr.png"),
    # G14 — DUYỆT CỬA HÀNG là việc công khai: khách xem giá và phụ kiện trước khi
    # để lại thông tin. Ba đường dưới đây CHỈ ĐỌC, chỉ trả sản phẩm đang bán, và
    # KHÔNG BAO GIỜ trả `cost_price` (giá nhập) — xem `docs/catalog.md` §5.
    # Mọi đường GHI (`/api/admin/products*`) vẫn bắt buộc `require_staff`.
    ("GET", "/api/catalog/categories"),
    ("GET", "/api/products"),
    ("GET", "/api/products/{slug}"),
}

#: Giá trị thay cho tham số đường dẫn khi dò.
DUMMY = {
    "gift_code": "VIP-26-ABCDEF",
    "lead_id": "00000000-0000-0000-0000-000000000000",
    "model_code": "iphone-16",
    "slug": "khong-ton-tai",
}


def api_routes():
    """Liệt kê mọi route /api từ OPENAPI SCHEMA của app.

    ⚠️  VÌ SAO KHÔNG ĐI QUA `app.routes`: FastAPI mới giữ router được include dưới
    dạng đối tượng lồng (`_IncludedRouter`) chứ không làm phẳng, nên duyệt
    `app.routes` sẽ **bỏ sót toàn bộ route của router con** — chính test này đã
    trả về 0 route ở lần viết đầu, tức là nó "đạt" một cách vô nghĩa.
    `app.openapi()` là nguồn ổn định hơn và không phụ thuộc bản FastAPI.
    """
    app = create_app(settings)
    schema = app.openapi()
    found = []
    for path, operations in schema.get("paths", {}).items():
        if not path.startswith("/api/"):
            continue
        for method in operations:
            if method.upper() in {"HEAD", "OPTIONS"}:
                continue
            found.append((method.upper(), path))
    return sorted(set(found))


def fill(path: str) -> str:
    out = path
    for name, value in DUMMY.items():
        out = out.replace("{" + name + "}", value)
    return out


def test_no_api_route_is_unexpectedly_public():
    """Mọi route /api không nằm trong danh sách công khai phải TỪ CHỐI khi không có khoá.

    Cách kiểm: gọi KHÔNG kèm khoá. Kết quả chấp nhận được là **401** (sai/thiếu khoá)
    hoặc **503** (máy chủ chưa cấu hình xác thực — fail closed). Bất kỳ mã nào khác,
    đặc biệt 200/201/204/405, nghĩa là route đang mở.
    """
    client = pytest.importorskip("fastapi.testclient").TestClient(create_app(settings))

    offenders = []
    checked = 0
    for method, path in api_routes():
        if (method, path) in PUBLIC_API_ROUTES:
            continue
        response = client.request(method, fill(path), json={})
        checked += 1
        if response.status_code not in (401, 403, 503):
            offenders.append((method, path, response.status_code))

    assert checked > 0, "không tìm thấy route /api nào để kiểm — test đang vô dụng"
    assert not offenders, (
        "Route /api sau KHÔNG đòi xác thực mà cũng không nằm trong danh sách công khai:\n"
        + "\n".join(f"  {m} {p} -> {code}" for m, p, code in offenders)
    )


def test_public_allowlist_matches_reality():
    """Danh sách công khai không được chứa route KHÔNG tồn tại.

    Nếu ai đó xoá một route mà quên xoá khỏi danh sách, test này đỏ — nhờ vậy danh
    sách không âm thầm phình ra và che mất một route mới.
    """
    real = set(api_routes())
    ghosts = sorted(PUBLIC_API_ROUTES - real)
    assert not ghosts, f"danh sách công khai chứa route không tồn tại: {ghosts}"


def test_known_admin_routes_are_protected(client):
    """Kiểm trực tiếp vài route nhạy cảm nhất — để thông điệp lỗi rõ ràng."""
    probes = [
        ("GET", "/api/admin/leads"),
        ("GET", "/api/admin/leads.csv"),
        ("POST", "/api/admin/iphone-models"),
        ("POST", "/api/gifts/VIP-26-ABCDEF/redeem"),
        ("GET", "/api/gifts/VIP-26-ABCDEF"),
    ]
    for method, path in probes:
        response = client.request(method, path, json={})
        assert response.status_code in (401, 403, 503), (
            f"{method} {path} trả {response.status_code} — KHÔNG được mở cho công khai"
        )


def test_redeem_mutation_is_not_reachable_without_key(client, valid_lead_payload):
    """Đường PHÁT QUÀ (đường ghi) phải khoá, kể cả khi mã tồn tại thật."""
    created = client.post("/api/leads", json=valid_lead_payload).json()

    response = client.post(f"/api/gifts/{created['gift_code']}/redeem", json={})
    assert response.status_code == 401, response.text

    # Và trạng thái KHÔNG được đổi.
    body = client.get(
        f"/api/gifts/{created['gift_code']}",
        headers={"X-Staff-Key": __import__("tests.conftest", fromlist=["STAFF_KEY"]).STAFF_KEY},
    ).json()
    assert body["gift_status"] == "NEW", "mã đã bị đổi trạng thái dù không có khoá"
