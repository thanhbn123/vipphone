"""Trang tĩnh mới của G04/G05: phục vụ được, và CSP vẫn NGHIÊM.

Vì sao có file này: `redeem.html` và `admin-leads.html` đều thêm script mới.
Nếu một trang rơi vào nhánh CSP nới (`/docs`) hoặc bị thêm `unsafe-inline`, mã
độc chèn vào trang quản trị sẽ chạy được — và đó là loại lỗi không có gì báo
động. Test ở đây đo **header thật do máy chủ trả về**, không grep file nguồn.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

PAGES = ("/", "/redeem.html", "/admin-leads.html")


@pytest.mark.parametrize("path", PAGES)
def test_page_is_served_with_strict_csp(client, path):
    response = client.get(path)
    assert response.status_code == 200, path

    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "style-src 'self'" in csp
    assert "unsafe-inline" not in csp, f"{path} được nới CSP bằng unsafe-inline"
    assert "frame-ancestors 'none'" in csp


@pytest.mark.parametrize("path", PAGES)
def test_page_is_not_cached(client, path):
    assert client.get(path).headers["Cache-Control"] == "no-store"


def test_admin_page_scripts_are_self_hosted(client):
    """Trang quản trị chỉ được nạp script từ chính origin (đường dẫn tương đối)."""
    html = client.get("/admin-leads.html").text
    assert 'src="assets/js/admin-leads.js"' in html
    assert "http://" not in html.replace("http://www.w3.org", "")
    assert "https://" not in html


def test_redeem_page_loads_the_qr_scanner_module(client):
    html = client.get("/redeem.html").text
    assert 'src="assets/js/qr-scan.js"' in html
    assert 'src="assets/js/redeem.js"' in html


def test_admin_api_errors_are_json_not_html(client):
    """Gọi API quản trị khi chưa xác thực phải trả JSON lỗi có cấu trúc."""
    response = client.get("/api/admin/leads")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert set(body["error"]) >= {"code", "message"}
