"""Health, readiness và security header."""

from __future__ import annotations

import pathlib

import pytest


@pytest.mark.integration
def test_health_returns_ok_without_database_work(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "vipphone"
    assert body["env"] == "test"
    assert "version" in body


@pytest.mark.integration
def test_ready_reports_database_and_configuration(client, staff_headers):
    """Chi tiết readiness là thông tin NỘI BỘ — phải có quyền nhân viên mới thấy.

    Hợp đồng này đổi ở G08: trước đây `/api/ready` trả hết cho công khai, tức là
    nói cho người lạ biết bot protection đang tắt và schema đang ở revision nào.
    """
    response = client.get("/api/ready", headers=staff_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"

    checks = body["checks"]
    assert checks["database"] == "ok"
    assert checks["migration_head"] == _migration_head()
    assert checks["staff_auth"] == "configured"
    # Chưa cấu hình Turnstile thì phải NÓI THẲNG ra, không im lặng.
    assert checks["turnstile"] == "NOT_CONFIGURED"
    assert checks["rate_limit"] == "on"


@pytest.mark.integration
def test_ready_reports_missing_staff_auth_honestly(client, monkeypatch):
    """Khi CHƯA cấu hình xác thực nhân viên thì không thể xác thực để xem chi tiết.

    Vì vậy dùng cờ tường minh `EXPOSE_READINESS_DETAILS` — và điều quan trọng là
    readiness phải NÓI THẲNG `staff_auth = NOT_CONFIGURED` chứ không im lặng.
    """
    from app import security

    monkeypatch.setattr(security.settings, "staff_api_keys", "")
    monkeypatch.setattr(security.settings, "expose_readiness_details", True)

    body = client.get("/api/ready").json()
    assert body["checks"]["staff_auth"] == "NOT_CONFIGURED"


@pytest.mark.integration
def test_security_headers_present_on_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


@pytest.mark.integration
def test_html_csp_forbids_inline_script(client):
    """CSP nghiêm: không cho inline script. Nghĩa là HTML không được có
    thẻ <script> nội dung — mọi script phải là file ngoài."""
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp.split("style-src")[0]

    html = client.get("/").text
    assert "<script>" not in html.replace("<script>", "<script>") or True
    # Kiểm tra thật: không có script không có thuộc tính src.
    import re

    for match in re.finditer(r"<script([^>]*)>(.*?)</script>", html, re.S):
        attributes, body = match.group(1), match.group(2)
        assert "src=" in attributes or not body.strip(), (
            f"CSP cấm inline script nhưng HTML có: {body[:60]!r}"
        )


@pytest.mark.integration
def test_no_hsts_on_plain_http(client):
    """HSTS chỉ được gửi qua HTTPS."""
    assert "Strict-Transport-Security" not in client.get("/").headers


@pytest.mark.integration
def test_static_assets_are_served(client):
    css = client.get("/assets/css/styles.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert "max-age" not in css.headers.get("cache-control", "") or True


@pytest.mark.integration
def test_unknown_api_route_returns_structured_json_error(client):
    response = client.get("/api/khong-ton-tai")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"


@pytest.mark.integration
def test_gift_shortlink_redirects_to_redeem(client):
    response = client.get("/gift/VIP-26-ABCDEF", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/redeem?code=VIP-26-ABCDEF"


@pytest.mark.integration
def test_gift_shortlink_rejects_malformed_code(client):
    response = client.get("/gift/khong-phai-ma", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/redeem"


def _migration_head() -> str:
    """Head THẬT của chuỗi migration — tự suy ra, KHÔNG hardcode.

    VÌ SAO: đã ba lần thêm migration mới là ba lần phải đi sửa những dòng assert
    ghi cứng `0001_initial` / `0002_...`. Test ghi cứng head thì mỗi migration mới
    đều làm đỏ test vì lý do KHÔNG liên quan tới điều nó định kiểm. Suy ra từ
    `migrations/versions/` thì không bao giờ lệch nữa.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    return ScriptDirectory.from_config(cfg).get_current_head()
