"""G08 — test hardening bảo mật.

Mỗi test ở đây phải **phân biệt được**: phá bản vá thì nó phải FAIL.
Xem `docs/MASTER_STATUS.md` §17 (một test PASS không có nghĩa là nó kiểm được gì).
"""

from __future__ import annotations

import asyncio
import pathlib
import re

import pytest

from app.errors import ApiError
from app.limits import BodyTooLarge, InvalidContentLength, read_limited_body

pytestmark = pytest.mark.integration


# =========================================================== F1: trần body
class _StubRequest:
    """Request giả tối thiểu cho `read_limited_body`."""

    def __init__(self, headers: dict[str, str], chunks: list[bytes] | None = None):
        self.headers = headers
        self._chunks = chunks or []
        self.stream_called = False

    async def stream(self):
        self.stream_called = True
        for chunk in self._chunks:
            yield chunk


def test_oversized_content_length_is_rejected_WITHOUT_reading_body():
    """TẤT ĐỊNH: vượt trần theo Content-Length thì phải từ chối TRƯỚC khi đọc.

    Đây là điểm mấu chốt của bản vá F1. Bản cũ đọc hết body vào RAM rồi mới
    kiểm, nên trần không bảo vệ được gì. Test này khẳng định `stream()` **không
    hề được gọi** — nếu ai quay lại lối đọc-trước-kiểm-sau, nó FAIL ngay.
    """
    request = _StubRequest({"content-length": "1048576"})

    with pytest.raises(BodyTooLarge):
        asyncio.run(read_limited_body(request, 8192))  # type: ignore[arg-type]

    assert request.stream_called is False, (
        "ĐÃ ĐỌC BODY dù Content-Length vượt trần — trần đang không bảo vệ gì."
    )


def test_body_within_limit_is_read():
    """Đối chứng dương: body trong trần thì phải đọc được bình thường."""
    request = _StubRequest({"content-length": "5"}, [b"hello"])
    assert asyncio.run(read_limited_body(request, 8192)) == b"hello"  # type: ignore[arg-type]


def test_chunked_body_without_content_length_is_capped():
    """Không có Content-Length (chunked) vẫn phải bị chặn theo từng khối."""
    chunks = [b"x" * 4096] * 4  # 16 KiB, trần 8 KiB
    request = _StubRequest({}, chunks)

    with pytest.raises(BodyTooLarge):
        asyncio.run(read_limited_body(request, 8192))  # type: ignore[arg-type]

    assert request.stream_called is True


def test_invalid_content_length_is_rejected():
    request = _StubRequest({"content-length": "khong-phai-so"})
    with pytest.raises(InvalidContentLength):
        asyncio.run(read_limited_body(request, 8192))  # type: ignore[arg-type]


def test_api_returns_413_for_oversized_payload(client):
    """Qua HTTP thật: payload vượt trần trả 413 với lỗi có cấu trúc."""
    big = b"x" * 20_000
    response = client.post(
        "/api/leads",
        content=big,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


# ================================================== F2: /api/ready lộ thông tin
def test_ready_public_does_not_leak_internals(client):
    """CÔNG KHAI chỉ được thấy `status`, không thấy chi tiết trạm gác."""
    response = client.get("/api/ready")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ready"
    assert set(body) == {"status"}, body
    for leaked in ("checks", "version", "env"):
        assert leaked not in body, f"rò {leaked} cho công khai"


def test_ready_with_staff_key_shows_details(client, staff_headers):
    """Đối chứng dương: nhân viên hợp lệ thì thấy đủ chi tiết."""
    body = client.get("/api/ready", headers=staff_headers).json()

    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["migration_head"] == _migration_head()
    assert body["checks"]["staff_auth"] == "configured"


def test_ready_hides_details_for_wrong_key(client):
    body = client.get("/api/ready", headers={"X-Staff-Key": "sai"}).json()
    assert set(body) == {"status"}, body


def test_ready_details_behind_explicit_flag(client, monkeypatch):
    """Bật cờ tường minh thì công khai thấy chi tiết — có chủ đích, không mặc định."""
    from app import security

    monkeypatch.setattr(security.settings, "expose_readiness_details", True)
    body = client.get("/api/ready").json()
    assert "checks" in body


# ========================================================= F4: Host header
def test_untrusted_host_is_rejected(client):
    """Host lạ phải bị chặn khi đã cấu hình ALLOWED_HOSTS."""
    response = client.get("/api/health", headers={"Host": "evil.example"})
    assert response.status_code == 400, (
        f"Host lạ được chấp nhận ({response.status_code}) — chưa chặn host header"
    )


def test_trusted_host_is_accepted(client):
    """Đối chứng dương: Host hợp lệ vẫn qua."""
    assert client.get("/api/health").status_code == 200


# ========================================================= F5: request id
def test_request_id_header_present_and_unique(client):
    first = client.get("/api/health")
    second = client.get("/api/health")

    first_id = first.headers.get("X-Request-ID")
    second_id = second.headers.get("X-Request-ID")

    assert first_id, "thiếu header X-Request-ID"
    assert second_id and second_id != first_id, "request id phải khác nhau mỗi request"
    # `request_id` là 16 ký tự hex (không phải UUID đầy đủ) — kiểm đúng dạng đó,
    # đừng kiểm UUID rồi tự làm mình đỏ.
    assert re.fullmatch(r"[0-9a-f]{16}", first_id), first_id


# ========================================================= F3: CORS
def test_no_cors_headers_for_foreign_origin(client):
    """API cùng origin nên KHÔNG được trả header CORS cho origin lạ.

    Nếu ai đó gắn `CORSMiddleware` với `allow_origins=["*"]`, test này FAIL.
    """
    response = client.get("/api/health", headers={"Origin": "https://evil.example"})
    for header in (
        "access-control-allow-origin",
        "access-control-allow-credentials",
    ):
        assert header not in response.headers, f"rò header CORS: {header}"


def test_dead_cors_config_removed():
    """Cấu hình CORS chết đã bị gỡ, không để lại thứ đọc như đã làm mà chưa làm."""
    from app.config import Settings

    fields = set(Settings.model_fields)
    assert "cors_allowed_origins" not in fields, (
        "CORS_ALLOWED_ORIGINS quay lại nhưng không có middleware nào dùng — cấu hình chết"
    )


# ============================================== header bảo mật vẫn còn nguyên
def test_security_headers_still_applied_after_changes(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


def test_body_too_large_is_api_error_subclass():
    assert issubclass(BodyTooLarge, ApiError)


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
