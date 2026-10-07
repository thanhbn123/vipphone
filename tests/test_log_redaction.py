"""Log không được chứa PII khách.

Hai lỗi THẬT đã đo được trước khi sửa:
1. `str(IntegrityError)` chứa "[parameters: {... '<họ tên>', '<SĐT>'}]" và mã ghi
   lỗi đó vào log ⇒ sửa bằng `hide_parameters=True` ở engine.
2. Access log uvicorn ghi nguyên query ⇒ `/api/admin/orders?q=<SĐT>` để lại SĐT
   trong log ⇒ sửa bằng `app/logredact.py`.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest
from sqlalchemy import text

from app.config import REPO_ROOT
from app.logredact import redact_path
from tests.conftest import STAFF_KEY, TEST_DATABASE_URL

pytestmark = pytest.mark.integration


def test_sql_errors_do_not_carry_bound_parameters():
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        with pytest.raises(Exception) as caught:
            session.execute(
                text(
                    "INSERT INTO leads (lead_id, gift_code, full_name, phone, iphone_model, "
                    "iphone_year, consent) VALUES (gen_random_uuid(), 'X', :n, :p, 'm', 2020, true)"
                ),
                {"n": "Nguyễn Bí Mật", "p": "0112345678"},
            )
        message = str(caught.value)
        # Lớp 1: SQLAlchemy không in tham số bind.
        assert "SQL parameters hidden due to hide_parameters=True" in message
        # Lớp 2: DETAIL của PostgreSQL VẪN chứa dữ liệu dòng — nên phải che ở log.
        from app.logredact import redact_text

        cleaned = redact_text(message)
        assert "Nguyễn Bí Mật" not in cleaned and "0112345678" not in cleaned
    finally:
        session.rollback()
        session.close()


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("/api/admin/orders?q=0912345678", "/api/admin/orders?q=***"),
        ("/api/admin/customers?phone=0912345678&limit=5", "/api/admin/customers?phone=***&limit=5"),
        ("/api/admin/orders?status=CONFIRMED", "/api/admin/orders?status=CONFIRMED"),
        ("/lookup/84912345678", "/lookup/***********"),
        ("/api/products?device_model=iphone-16", "/api/products?device_model=iphone-16"),
    ],
)
def test_redact_path(raw, expected):
    assert redact_path(raw) == expected


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_real_uvicorn_access_log_has_no_phone(tmp_path):
    port = _free_port()
    log_path = tmp_path / "uvicorn.log"
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DATABASE_URL,
        "STAFF_API_KEYS": STAFF_KEY,
        "ALLOWED_HOSTS": "127.0.0.1,localhost",
        "LOG_LEVEL": "info",
        "PYTHONPATH": str(REPO_ROOT),
    }
    with log_path.open("w") as log:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--port",
                str(port),
                "--log-level",
                "info",
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        for path in ("/api/admin/orders?q=0912345678", "/api/admin/customers?phone=0987654321"):
            req = urllib.request.Request(base + path, headers={"X-Staff-Key": STAFF_KEY})
            urllib.request.urlopen(req, timeout=5).read()
        time.sleep(0.5)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    content = log_path.read_text()
    assert "/api/admin/orders?q=***" in content, content[-2000:]
    assert "0912345678" not in content and "0987654321" not in content


def test_error_redactor_cleans_traceback_and_message():
    import logging

    from app.logredact import ErrorRedactor

    try:
        raise RuntimeError(
            "CheckViolation\nDETAIL:  Failing row contains (1, Nguyễn Bí Mật, 0112345678).\n"
            "[parameters: {'p': '0112345678'}]"
        )
    except RuntimeError:
        import sys

        record = logging.LogRecord(
            "x", logging.ERROR, __file__, 1, "lỗi: %s", ("0112345678 DETAIL: x y",), sys.exc_info()
        )
    ErrorRedactor().filter(record)
    handler_output = logging.Formatter().format(record)
    assert "Nguyễn Bí Mật" not in handler_output
    assert "0112345678" not in handler_output.split("lỗi:")[1].split("DETAIL")[1]
    assert "Failing row" not in handler_output


def test_unhandled_db_error_in_real_server_log_has_no_pii(tmp_path):
    """Lỗi DB KHÔNG được bắt trong request ⇒ uvicorn ghi traceback — phải đã che."""
    port = _free_port()
    log_path = tmp_path / "uvicorn.log"
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DATABASE_URL,
        "STAFF_API_KEYS": STAFF_KEY,
        "ALLOWED_HOSTS": "127.0.0.1,localhost",
        "LOG_LEVEL": "info",
        "PYTHONPATH": str(REPO_ROOT),
        "VIPPHONE_TEST_CRASH_ROUTE": "1",
    }
    with log_path.open("w") as log:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.crash_app:app",
                "--port",
                str(port),
                "--log-level",
                "info",
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        try:
            urllib.request.urlopen(base + "/__crash", timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 500
        time.sleep(0.5)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    content = log_path.read_text()
    assert "CheckViolation" in content, content[-3000:]
    assert "Nguyễn Bí Mật" not in content and "0112345678" not in content, content[-3000:]
