"""Bộ khung test E2E: máy chủ thật + PostgreSQL thật + Chromium thật.

VÌ SAO CẦN LỚP NÀY (đọc trước khi sửa):

Test trong `tests/` đo tầng API. Nhưng hai yêu cầu của gate G04/G06 chỉ đo được
bằng **trình duyệt thật**:

- "thêm model qua API admin → **landing** thấy model đó": `tests/` chỉ chứng minh
  API danh mục trả về model; nó KHÔNG chứng minh được landing vẽ ra `<option>`.
- "phải **ẩn nút** quét QR khi không hỗ trợ — không được giả vờ": đây là hành vi
  của DOM dưới một năng lực trình duyệt cụ thể. Không có cách nào đo bằng API.
- "khoá nhân viên **không** lưu lâu dài": phải đọc `localStorage` THẬT của một
  trình duyệt THẬT sau khi thao tác thật.

Lớp này KHÔNG chạy trong CI (CI chỉ chạy `tests/`). Chạy tay bằng `make test-e2e`.
Nếu Chromium chưa cài, bộ này **báo lỗi rõ ràng** chứ không tự bỏ qua: một test
E2E bị skip im lặng là một test không bao giờ có thể FAIL (xem MASTER_STATUS §17).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# `tests_e2e/` không phải một package, nên gốc repo có thể chưa nằm trên `sys.path`
# (chỉ chắc chắn có khi chạy `python -m pytest`). Chèn tường minh để `from tests.*
# import ...` chạy được với mọi cách gọi.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Dùng CHUNG nguồn với `tests/` để hai bên không lệch nhau: khoá nhân viên của
# test, chốt an toàn `_test`, hàm dựng migration, và dữ liệu seed danh mục.
from tests.conftest import (  # noqa: E402
    STAFF_KEY,
    TEST_DATABASE_URL,
    alembic_config,
    reset_public_schema,
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, process: subprocess.Popen, *, timeout: float = 60.0) -> None:
    """Chờ máy chủ sống. Nếu tiến trình chết trước đó thì nói NGAY, kèm log."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"uvicorn thoát sớm với mã {process.returncode}:\n{_read_log()}")
        try:
            with urllib.request.urlopen(base_url + "/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    raise RuntimeError(f"máy chủ không lên sau {timeout:.0f}s:\n{_read_log()}")


LOG_PATH = Path("/tmp/vipphone-e2e-uvicorn.log")


def _read_log() -> str:
    try:
        return LOG_PATH.read_text()[-3000:]
    except OSError:
        return "(không đọc được log)"


@pytest.fixture(scope="session")
def live_server() -> str:
    """Máy chủ uvicorn THẬT trên database test (tên kết thúc bằng `_test`).

    Tiến trình do chính fixture này khởi động nên tắt bằng `terminate()` trên
    đúng đối tượng Popen — không săn tiến trình theo tên (CLAUDE.md §16.7).
    """
    from alembic import command

    reset_public_schema(TEST_DATABASE_URL)
    command.upgrade(alembic_config(TEST_DATABASE_URL), "head")

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DATABASE_URL,
        "PUBLIC_BASE_URL": base_url,
        "STAFF_API_KEYS": STAFF_KEY,
        "RATE_LIMIT_ENABLED": "false",
        "TURNSTILE_SECRET_KEY": "",
        "TURNSTILE_REQUIRED": "false",
        "LOG_LEVEL": "warning",
        "PYTHONPATH": str(REPO_ROOT),
    }

    with LOG_PATH.open("w") as log:
        process = subprocess.Popen(
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
                "warning",
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )

    try:
        _wait_for_health(base_url, process)
        os.environ["E2E_BASE_URL"] = base_url
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - chỉ khi treo
            process.kill()
            process.wait(timeout=5)


#: Ba engine được hỗ trợ. Chọn bằng biến môi trường để CI chạy được MA TRẬN
#: mà không cần parametrize fixture cấp session (vốn rất khó viết đúng).
SUPPORTED_BROWSERS = ("chromium", "firefox", "webkit")


def selected_browser() -> str:
    """Engine đang chọn. Mặc định `chromium`; sai tên thì DỪNG ngay.

    Dừng ngay thay vì âm thầm dùng chromium: gõ sai tên mà vẫn chạy được nghĩa là
    CI có thể tưởng đang kiểm WebKit trong khi thật ra chỉ chạy lại Chromium.
    """
    name = os.environ.get("E2E_BROWSER", "chromium").strip().lower()
    if name not in SUPPORTED_BROWSERS:
        raise RuntimeError(
            f"E2E_BROWSER={name!r} không hợp lệ. Chọn một trong {SUPPORTED_BROWSERS}."
        )
    return name


@pytest.fixture(scope="session")
def browser():
    """Trình duyệt THẬT, headless. Thiếu trình duyệt thì BÁO LỖI, không skip."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    name = selected_browser()

    with sync_playwright() as playwright:
        engine = getattr(playwright, name)
        try:
            instance = engine.launch(headless=True)
        except PlaywrightError as exc:  # pragma: no cover - phụ thuộc máy
            raise RuntimeError(
                f"Không mở được {name} của Playwright. Cài bằng:\n"
                f"    .venv/bin/playwright install {name}\n"
                f"Lỗi gốc: {exc}"
            ) from exc
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture(scope="session")
def browser_name() -> str:
    """Tên engine đang chạy — để test có thể tự bỏ qua phần không hỗ trợ."""
    return selected_browser()


def pytest_report_header(config) -> str:
    return f"VIP PHONE E2E — trình duyệt: {selected_browser()}"


@pytest.fixture
def console_errors() -> list[str]:
    """Nơi hứng lỗi console/JS của trang. Test nào cần thì xin fixture này."""
    return []


@pytest.fixture
def page(browser, console_errors):
    context = browser.new_context()
    page = context.new_page()

    # CSP vi phạm và lỗi JS hiện ra ở console. Đây là phép đo THẬT cho yêu cầu
    # "không inline script/style/handler" — mạnh hơn grep nội dung file.
    page.on(
        "console",
        lambda message: message.type == "error" and console_errors.append(message.text),
    )
    page.on("pageerror", lambda error: console_errors.append(str(error)))

    try:
        yield page
    finally:
        context.close()


@pytest.fixture(autouse=True)
def clean_database(live_server) -> None:
    """Mỗi test bắt đầu từ database sạch, danh mục dựng lại như migration."""
    from sqlalchemy import create_engine, text

    from tests.conftest import INITIAL_MIGRATION

    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE audit_events, leads RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE TABLE iphone_models RESTART IDENTITY CASCADE"))
            conn.execute(INITIAL_MIGRATION.MODELS_TABLE.insert(), INITIAL_MIGRATION.seed_rows())
    finally:
        engine.dispose()


# =============================================================================
# BỔ SUNG CHO BỘ E2E "FUNNEL" — DÁN VÀO CUỐI `tests_e2e/conftest.py`
#
# Cố ý CHỈ THÊM, KHÔNG SỬA phần phía trên. Hai lý do:
#   1. Phần trên là của gate G04-G06, đã được đo bằng bộ test của họ. Sửa vào đó
#      là làm hỏng phép đo của người khác mà không có lợi gì.
#   2. Thêm mới thì gộp không thể xung đột: hai bộ test dùng hai tên fixture khác
#      nhau (`page` của họ, `funnel_page` của tôi) trên cùng một `browser`.
#
# VÌ SAO CẦN `funnel_page` RIÊNG: `window.dataLayer` là biến của TỪNG TRANG, nên
# đọc nó sau khi điều hướng sẽ MẤT event của trang trước. Đó là lỗi phép đo đã
# dính thật (MASTER_STATUS §17 ca 3): test báo "gift_code_created không phát ra"
# trong khi event có phát — chỉ là đã bị mất khi sang trang. `funnel_page` gắn
# thêm một bộ ghi vào `sessionStorage` để event sống sót qua điều hướng.
# =============================================================================

EVENTS_STORAGE_KEY = "__e2e_events__"


@pytest.fixture
def server(live_server) -> dict:
    """Gói thông tin máy chủ cho bộ test funnel.

    `live_server` của gate trả về CHUỖI base_url. Bộ funnel cần thêm khoá nhân
    viên và URL database, nên bọc lại thành dict — KHÔNG đổi `live_server`, để
    bộ test của gate không phải sửa gì.
    """
    return {
        "base_url": live_server,
        "staff_key": STAFF_KEY,
        "database_url": TEST_DATABASE_URL,
    }


@pytest.fixture
def funnel_page(browser):
    """Trang có bộ ghi dataLayer BỀN QUA CÁC LẦN ĐIỀU HƯỚNG."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.add_init_script(
        """
        (function () {
            window.dataLayer = window.dataLayer || [];
            var KEY = '__e2e_events__';
            var record = function (arg) {
                try {
                    var list = JSON.parse(sessionStorage.getItem(KEY) || '[]');
                    list.push(arg && arg.event ? arg.event : String(arg));
                    sessionStorage.setItem(KEY, JSON.stringify(list));
                } catch (e) {}
            };
            var original = window.dataLayer.push.bind(window.dataLayer);
            window.dataLayer.push = function () {
                for (var i = 0; i < arguments.length; i++) record(arguments[i]);
                return original.apply(null, arguments);
            };
        })();
        """
    )
    try:
        yield page
    finally:
        context.close()


@pytest.fixture
def mobile_context(browser):
    """Tạo ngữ cảnh trình duyệt với cỡ khung nhìn cho trước (để đo trên điện thoại)."""
    created: list = []

    def _make(width: int, height: int):
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        created.append(context)
        return page

    try:
        yield _make
    finally:
        for context in created:
            context.close()


def recorded_events(page) -> list[str]:
    """Mọi `dataLayer` event đã phát, GỘP QUA CÁC LẦN ĐIỀU HƯỚNG.

    Đọc từ `sessionStorage` (bộ ghi của `funnel_page`), KHÔNG đọc
    `window.dataLayer` — vì biến đó chỉ thuộc trang hiện tại.
    """
    return page.evaluate(f"JSON.parse(sessionStorage.getItem('{EVENTS_STORAGE_KEY}') || '[]')")
