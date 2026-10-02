"""STG-2 — /favicon.ico phải trả 204 KHÔNG body, và KHÔNG được làm uvicorn ném lỗi.

VÌ SAO TEST NÀY KHÁC CÁC TEST KHÁC: `TestClient` gọi thẳng ASGI app, **bỏ qua tầng
HTTP của uvicorn** — nên nó KHÔNG thấy lỗi `Response content longer than
Content-Length`. Đó chính là lý do bộ test hiện có không bắt được STG-2.

Test này khởi động **uvicorn thật** rồi đọc `stderr` của nó.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_favicon_returns_204_with_no_body_and_no_server_error():
    port = _free_port()
    env = {
        **os.environ,
        "APP_ENV": "test",
        "ALLOWED_HOSTS": "127.0.0.1,localhost",
        "PUBLIC_BASE_URL": f"http://127.0.0.1:{port}",
        "STAFF_API_KEYS": "staff-key-for-tests-only",
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "info",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
                break
            except Exception:
                if proc.poll() is not None:
                    raise AssertionError("uvicorn thoát sớm") from None
                time.sleep(0.5)
        else:
            raise AssertionError("uvicorn không lên được")

        # Gọi favicon NHIỀU LẦN: lỗi xảy ra ở MỌI request, không phải thỉnh thoảng.
        for _ in range(5):
            try:
                resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/favicon.ico", timeout=5)
                assert resp.status == 204, f"mong 204, nhận {resp.status}"
                assert resp.read() == b"", "204 KHÔNG được có body"
            except urllib.error.HTTPError as exc:
                pytest.fail(f"favicon trả HTTP {exc.code} thay vì 204")

        time.sleep(0.5)
        proc.terminate()
        out = proc.communicate(timeout=10)[0] or ""
    finally:
        if proc.poll() is None:
            proc.kill()

    # CHỐT QUAN TRỌNG NHẤT — đây là thứ bộ test cũ không kiểm được.
    assert "Response content longer than Content-Length" not in out, (
        "uvicorn ném 'Response content longer than Content-Length' — favicon đang "
        f"gửi body cho response 204.\n--- log ---\n{out[-1500:]}"
    )
    assert "Traceback" not in out, f"có Traceback trong log uvicorn:\n{out[-1500:]}"
