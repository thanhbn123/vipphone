"""E2E trình duyệt thật cho G04 (redeem UI + quét QR) và G06 (danh mục iPhone).

MỌI test ở đây **đã được kiểm bằng đối chứng âm** (phá thứ nó bảo vệ → FAIL).
Kết quả đo ghi ở `docs/MASTER_STATUS.md` §20. Chạy: `make test-e2e`.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

NEW_MODEL = {
    "model_code": "iphone-17-pro",
    "display_name": "iPhone 17 Pro",
    "year": 2027,
    "sort_order": -5,
    "active": True,
}


# ---------------------------------------------------------------- tiện ích


def api(base_url: str, path: str, *, method: str = "GET", key: str | None = None, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(base_url + path, data=data, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    if key:
        request.add_header("X-Staff-Key", key)
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = response.read()
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload


def html_fingerprints() -> dict[str, str]:
    """SHA-256 của mọi file `.html` ở gốc repo — mốc so sánh BYTE."""
    result = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in REPO_ROOT.glob("*.html")
    }
    assert result, "không có file HTML nào để đo"
    return result


def create_gift(base_url: str, **overrides) -> dict:
    payload = {
        "full_name": "Nguyễn Văn A",
        "phone": "0912345678",
        "iphone_model": "iphone-16-pro-max",
        "case_color": "Đen",
        "source": "bni",
        "consent": True,
        **overrides,
    }
    request = urllib.request.Request(
        base_url + "/api/leads", data=json.dumps(payload).encode("utf-8"), method="POST"
    )
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status == 201
        return json.loads(response.read())


# ==========================================================================
# G06 — LANDING THẤY MODEL MỚI MÀ KHÔNG SỬA HTML
# ==========================================================================


def test_landing_shows_model_added_through_admin_api(page, live_server, staff_key):
    """ĐO BẰNG TRÌNH DUYỆT THẬT: thêm model qua API admin → `<option>` xuất hiện.

    Đồng thời đo băm BYTE của mọi file `.html` trước/sau: không file nào đổi.

    Đối chứng âm (đã chạy, ghi ở MASTER_STATUS §20): bỏ phần `fetch` danh mục
    trong `assets/js/app.js`, thay bằng danh sách cứng → test này FAIL.
    """
    before_html = html_fingerprints()

    api(live_server, "/api/admin/iphone-models", method="POST", key=staff_key, body=NEW_MODEL)

    page.goto(live_server + "/", wait_until="load")

    # Landing nạp danh mục bằng fetch; chờ cho `<select>` có dữ liệu thật.
    page.wait_for_function(
        "() => document.querySelectorAll('#iphone_model option').length > 1",
        timeout=10_000,
    )

    options = page.eval_on_selector_all(
        "#iphone_model option", "els => els.map(e => ({value: e.value, text: e.textContent}))"
    )
    values = [option["value"] for option in options]
    assert "iphone-17-pro" in values, f"landing không thấy model mới: {values}"
    # sort_order = -5 ⇒ đứng đầu, sau option rỗng "Đang tải/Chọn".
    assert values[1] == "iphone-17-pro"

    labels = [option["text"] for option in options]
    assert "iPhone 17 Pro" in labels

    assert html_fingerprints() == before_html, "thêm model mà có file HTML bị đổi"


def test_landing_hides_a_model_deactivated_through_admin_api(page, live_server, staff_key):
    """Tắt model qua admin → landing KHÔNG còn hiện nó (đo trên DOM thật)."""
    page.goto(live_server + "/", wait_until="load")
    page.wait_for_function(
        "() => document.querySelectorAll('#iphone_model option').length > 1", timeout=10_000
    )
    assert "iphone-16-pro-max" in page.eval_on_selector_all(
        "#iphone_model option", "els => els.map(e => e.value)"
    )

    api(
        live_server,
        "/api/admin/iphone-models/iphone-16-pro-max",
        method="PATCH",
        key=staff_key,
        body={"active": False},
    )

    page.reload(wait_until="load")
    page.wait_for_function(
        "() => document.querySelectorAll('#iphone_model option').length > 1", timeout=10_000
    )
    assert "iphone-16-pro-max" not in page.eval_on_selector_all(
        "#iphone_model option", "els => els.map(e => e.value)"
    )


# ==========================================================================
# G04 — NÚT QUÉT QR: ẨN KHI KHÔNG HỖ TRỢ, HIỆN KHI HỖ TRỢ
# ==========================================================================

#: Giả lập trình duyệt KHÔNG có API quét QR.
SCRIPT_NO_BARCODE_DETECTOR = """
Object.defineProperty(window, 'BarcodeDetector', {
  value: undefined, configurable: true, writable: true
});
"""

#: Giả lập trình duyệt CÓ API quét QR (Chromium thật vẫn chạy phần còn lại).
SCRIPT_WITH_BARCODE_DETECTOR = """
window.BarcodeDetector = class {
  static getSupportedFormats() { return Promise.resolve(['qr_code']); }
  constructor() {}
  detect() { return Promise.resolve([]); }
};
// GHI ĐÈ vô điều kiện: Chromium thật ĐÃ có `getUserMedia`, nên điều kiện
// `!getUserMedia` sẽ không bao giờ đúng và camera thật sẽ bị gọi (headless
// không có camera ⇒ NotFoundError ⇒ test đo nhầm đường).
if (navigator.mediaDevices) {
  Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
    value: () => Promise.resolve(new MediaStream()),
    configurable: true,
    writable: true
  });
}
"""


def script_with_qr_payload(payload: str) -> str:
    """Cùng bộ giả lập trên, nhưng `detect()` trả về đúng một mã cho trước."""
    return SCRIPT_WITH_BARCODE_DETECTOR.replace(
        "detect() { return Promise.resolve([]); }",
        "detect() { return Promise.resolve([{ rawValue: " + json.dumps(payload) + " }]); }",
    )


def test_qr_scan_button_hidden_when_browser_does_not_support_it(page, live_server):
    """Không hỗ trợ `BarcodeDetector` ⇒ nút quét PHẢI ẩn, và phải nói rõ lý do.

    Đối chứng âm (đã chạy, MASTER_STATUS §20): bỏ điều kiện hỗ trợ trong
    `assets/js/redeem.js` (hiện nút vô điều kiện) → test này FAIL.
    """
    page.add_init_script(SCRIPT_NO_BARCODE_DETECTOR)
    page.goto(live_server + "/redeem.html", wait_until="load")
    page.wait_for_timeout(400)

    assert page.evaluate("typeof window.BarcodeDetector") == "undefined", "chưa giả lập được"

    toggle = page.locator("#scanToggle")
    assert toggle.count() == 1, "trang thiếu nút quét"
    assert not toggle.is_visible(), "nút quét HIỆN dù trình duyệt không hỗ trợ — đang giả vờ"

    explanation = page.locator("#scanUnsupported")
    assert explanation.is_visible(), "không hỗ trợ mà không nói gì với người dùng"
    assert "không" in explanation.inner_text().lower()


def test_qr_scan_button_appears_when_browser_supports_it(page, live_server):
    """Có `BarcodeDetector` + camera ⇒ nút quét PHẢI hiện và mở được khung quét.

    Đây là đối chứng DƯƠNG của test trên: không có nó thì test trên chỉ chứng
    minh được "nút luôn ẩn", chứ không chứng minh được logic hỗ trợ chạy đúng.
    """
    page.add_init_script(SCRIPT_WITH_BARCODE_DETECTOR)
    page.goto(live_server + "/redeem.html", wait_until="load")

    toggle = page.locator("#scanToggle")
    toggle.wait_for(state="visible", timeout=5000)
    assert page.locator("#scanUnsupported").is_hidden()

    toggle.click()
    page.locator("#scanPanel").wait_for(state="visible", timeout=5000)
    assert toggle.get_attribute("aria-expanded") == "true"

    page.locator("#scanStop").click()
    page.wait_for_timeout(200)
    assert page.locator("#scanPanel").is_hidden()


def test_qr_scanning_a_wrong_qr_does_not_pretend_success(page, live_server):
    """Quét được một QR KHÔNG phải phiếu quà ⇒ nói thẳng, KHÔNG tra cứu bừa."""
    page.add_init_script(script_with_qr_payload("https://evil.example/khong-phai"))
    page.goto(live_server + "/redeem.html", wait_until="load")
    page.locator("#scanToggle").wait_for(state="visible", timeout=5000)
    page.locator("#scanToggle").click()

    page.wait_for_function(
        "() => (document.getElementById('scanStatus').textContent || '').includes('không phải phiếu quà')",
        timeout=10_000,
    )
    status = page.locator("#scanStatus").inner_text().lower()
    assert "không phải phiếu quà" in status, status
    # Không được nhét mã rác vào ô và cũng không được gọi API tra cứu.
    assert page.input_value("#redeemCode") == ""


def test_qr_scanning_a_real_gift_qr_fills_the_code(page, live_server, staff_key):
    """Đối chứng DƯƠNG: QR ĐÚNG phải được nhận, điền vào ô và tra cứu ra phiếu quà."""
    created = create_gift(live_server)
    redeem_url = f"{live_server}/redeem?code={created['gift_code']}"

    page.add_init_script(script_with_qr_payload(redeem_url))
    page.goto(live_server + "/redeem.html", wait_until="load")
    page.fill("#staffKey", staff_key)
    page.locator("#scanToggle").wait_for(state="visible", timeout=5000)
    page.locator("#scanToggle").click()

    page.locator(".detail-list").wait_for(state="visible", timeout=10_000)
    assert page.input_value("#redeemCode") == created["gift_code"]


# ==========================================================================
# G04 — KHOÁ NHÂN VIÊN CHỈ SỐNG TRONG PHIÊN
# ==========================================================================


@pytest.fixture
def staff_key() -> str:
    from tests.conftest import STAFF_KEY

    return STAFF_KEY


def test_staff_key_is_kept_in_session_storage_only(page, live_server, staff_key):
    """Sau một lần tra cứu THẬT: khoá nằm ở `sessionStorage`, KHÔNG ở `localStorage`.

    Đối chứng âm (đã chạy, MASTER_STATUS §20): thêm một dòng
    `localStorage.setItem(...)` vào `assets/js/redeem.js` → test này FAIL.
    """
    created = create_gift(live_server)

    page.goto(live_server + "/redeem.html", wait_until="load")
    page.fill("#staffKey", staff_key)
    page.fill("#redeemCode", created["gift_code"])
    page.click("button[type=submit]")

    page.locator(".detail-list").wait_for(state="visible", timeout=10_000)

    session_value = page.evaluate("() => sessionStorage.getItem('vipphone_staff_key_v1')")
    local_dump = page.evaluate("() => JSON.stringify(Object.entries(localStorage))")

    assert session_value == staff_key, "khoá không được giữ trong phiên"
    assert staff_key not in local_dump, f"khoá bị lưu lâu dài: {local_dump}"
    assert "vipphone_staff_key_v1" not in local_dump


def test_redeem_flow_confirms_gift_and_shows_redeemed_state(page, live_server, staff_key):
    """Luồng G04 đầy đủ trên trình duyệt thật: tra cứu → xác nhận → trạng thái đã phát."""
    created = create_gift(live_server)

    page.goto(live_server + f"/redeem.html?code={created['gift_code']}", wait_until="load")
    page.fill("#staffKey", staff_key)
    page.click("button[type=submit]")

    page.locator("#confirmRedeem").wait_for(state="visible", timeout=10_000)
    detail = page.locator(".detail-list").inner_text()
    assert "0912***678" in detail, "SĐT phải được che ở màn nhân viên"
    assert "0912345678" not in detail, "SĐT đầy đủ bị lộ ở màn nhân viên"

    page.click("#confirmRedeem")
    page.wait_for_function(
        "() => document.querySelector('#redeemResult').innerText.includes('thành công')",
        timeout=10_000,
    )
    assert "thành công" in page.locator("#redeemResult").inner_text().lower()

    page.reload(wait_until="load")
    page.fill("#staffKey", staff_key)
    page.click("button[type=submit]")
    # Chờ ĐÚNG câu cần kiểm, không chờ "có hộp trạng thái nào đó": hộp
    # "Đang tra cứu…" cũng khớp điều kiện rộng, và test sẽ đọc nhầm trạng thái
    # trung gian (đã dính một lần ở chính test này).
    page.wait_for_function(
        "() => document.querySelector('#redeemResult').innerText.includes('đã được nhận quà')",
        timeout=10_000,
    )
    text = page.locator("#redeemResult").inner_text().lower()
    assert "đã được nhận quà" in text, text
    assert page.locator("#confirmRedeem").count() == 0


# ==========================================================================
# G05 — TRANG QUẢN TRỊ TRÊN TRÌNH DUYỆT THẬT
# ==========================================================================


def test_admin_page_renders_leads_without_console_or_csp_errors(
    page, live_server, staff_key, console_errors
):
    """Trang quản trị chạy sạch dưới CSP nghiêm, và KHÔNG lộ SĐT khi thiếu khoá."""
    created = create_gift(live_server, full_name="Khách Kiểm Thử")

    page.goto(live_server + "/admin-leads.html", wait_until="load")

    # Chưa nhập khoá: KHÔNG được hiện dữ liệu khách.
    assert "Khách Kiểm Thử" not in page.content()
    assert "0912345678" not in page.content()

    page.fill("#staffKey", staff_key)
    page.click("#searchBtn")

    page.locator("#leadRows tr td").first.wait_for(state="visible", timeout=10_000)
    page.wait_for_function(
        "() => document.getElementById('leadRows').innerText.includes('"
        + created["gift_code"]
        + "')",
        timeout=10_000,
    )

    body_text = page.locator("#leadRows").inner_text()
    assert "Khách Kiểm Thử" in body_text

    # Chi tiết: bấm "Xem" của dòng đầu.
    page.locator("#leadRows button", has_text="Xem").first.click()
    # Chờ ĐÚNG thứ sắp khẳng định (mã quà), không chờ một tiêu đề tĩnh.
    # Tiêu đề "Chi tiết lead" có thể hiện ra trước khi nội dung được đổ vào — cùng
    # loại race với `test_admin_page_adds_a_model_and_landing_sees_it`.
    page.wait_for_function(
        "(code) => document.getElementById('detailBox').innerText.includes(code)",
        arg=created["gift_code"],
        timeout=10_000,
    )
    assert created["gift_code"] in page.locator("#detailBox").inner_text()

    assert console_errors == [], f"trang quản trị có lỗi console/CSP: {console_errors}"


def test_admin_page_exports_csv_through_the_browser(page, live_server, staff_key):
    """Nút XUẤT CSV phải tải được file THẬT, đúng bộ lọc, và có header chống injection."""
    create_gift(live_server, full_name="=1+1", phone="0912345678")
    create_gift(live_server, full_name="Khách Thường", phone="0987654321")

    page.goto(live_server + "/admin-leads.html", wait_until="load")
    page.fill("#staffKey", staff_key)
    page.click("#searchBtn")
    page.wait_for_function(
        "() => document.getElementById('leadRows').innerText.includes('Khách Thường')",
        timeout=10_000,
    )

    # Áp bộ lọc SĐT rồi export: file phải CHỈ có dòng khớp bộ lọc.
    page.fill("#fPhone", "0987")
    page.click("#searchBtn")
    page.wait_for_function(
        "() => document.getElementById('statusLine').innerText.includes('1 lead')",
        timeout=10_000,
    )

    with page.expect_download(timeout=15_000) as download_info:
        page.click("#exportBtn")
    download = download_info.value

    path = download.path()
    content = Path(path).read_text(encoding="utf-8")

    assert download.suggested_filename.startswith("vipphone-leads-")
    assert "Khách Thường" in content
    # Bộ lọc SĐT "0987" chỉ khớp một lead ⇒ lead còn lại KHÔNG được có trong file.
    assert "=1+1" not in content, "CSV không dùng cùng bộ lọc với danh sách"


def test_admin_page_adds_a_model_and_landing_sees_it(page, live_server, staff_key, console_errors):
    """Thêm model NGAY TRÊN UI admin → landing thấy model đó. Không sửa HTML."""
    before_html = html_fingerprints()

    page.goto(live_server + "/admin-leads.html", wait_until="load")
    page.fill("#staffKey", staff_key)
    page.click("#searchBtn")
    page.wait_for_function(
        "() => document.getElementById('modelRows').innerText.includes('iPhone 16 Pro Max')",
        timeout=10_000,
    )

    page.fill("#mCode", "iphone-17-pro")
    page.fill("#mName", "iPhone 17 Pro")
    page.fill("#mYear", "2027")
    page.fill("#mSort", "-5")
    page.click("#modelSubmit")

    page.wait_for_function(
        "() => document.getElementById('modelStatus').innerText.includes('Đã thêm')",
        timeout=10_000,
    )

    # PHẢI CHỜ BẢNG VẼ LẠI, không được assert ngay.
    #
    # VÌ SAO: `admin-leads.js` đặt chữ "Đã thêm" TRƯỚC rồi mới gọi `loadModels()`
    # — hai việc KHÁC NHAU. Chờ chữ "Đã thêm" rồi assert bảng ngay là đọc bảng
    # TRƯỚC KHI nó được vẽ lại. Trên máy nhanh thì thắng race; trên CI chậm hơn
    # thì thua ⇒ test ĐỎ vì lý do không liên quan tới sản phẩm.
    #
    # Đã đo, không suy đoán: tiêm độ trễ 1,5 giây ngay trước `loadModels()` thì
    # test bản cũ FAIL đúng y hệt lỗi thấy trên CI
    # (`assert 'iphone-17-pro' in 'iphone-16\tiPhone 16…'`). Bản này chờ đúng
    # điều kiện đang được khẳng định nên vượt qua cả khi có độ trễ.
    page.wait_for_function(
        "() => document.getElementById('modelRows').innerText.includes('iphone-17-pro')",
        timeout=10_000,
    )
    assert "iphone-17-pro" in page.locator("#modelRows").inner_text()

    # Landing: mở tab mới, đọc `<option>` thật.
    landing = page.context.new_page()
    landing.goto(live_server + "/", wait_until="load")
    landing.wait_for_function(
        "() => document.querySelectorAll('#iphone_model option').length > 1", timeout=10_000
    )
    values = landing.eval_on_selector_all("#iphone_model option", "els => els.map(e => e.value)")
    landing.close()

    assert "iphone-17-pro" in values
    assert html_fingerprints() == before_html
    assert console_errors == [], console_errors


def test_admin_page_rejects_an_invalid_model_code_from_the_ui(page, live_server, staff_key):
    """UI không được nuốt lỗi validate: mã sai phải hiện thông báo và KHÔNG tạo model."""
    page.goto(live_server + "/admin-leads.html", wait_until="load")
    page.fill("#staffKey", staff_key)
    page.click("#searchBtn")
    page.wait_for_function(
        "() => document.getElementById('modelRows').innerText.includes('iPhone')", timeout=10_000
    )

    page.fill("#mCode", "IPHONE SAI")
    page.fill("#mName", "iPhone Sai")
    page.fill("#mYear", "2027")
    page.click("#modelSubmit")

    page.wait_for_function(
        "() => document.getElementById('modelError').hidden === false", timeout=10_000
    )
    error_text = page.locator("#modelError").inner_text()
    assert "model_code" in error_text or "model" in error_text.lower()

    models = api(live_server, "/api/admin/iphone-models", key=staff_key)
    assert "iphone sai" not in {model["model_code"] for model in models}
    assert "IPHONE SAI" not in {model["model_code"] for model in models}


def test_admin_page_rejects_year_before_2007_from_the_ui(page, live_server, staff_key):
    page.goto(live_server + "/admin-leads.html", wait_until="load")
    page.fill("#staffKey", staff_key)
    page.click("#searchBtn")
    page.wait_for_function(
        "() => document.getElementById('modelRows').innerText.includes('iPhone')", timeout=10_000
    )

    page.fill("#mCode", "iphone-cu")
    page.fill("#mName", "iPhone Cũ")
    page.fill("#mYear", "1999")
    page.click("#modelSubmit")

    page.wait_for_function(
        "() => document.getElementById('modelError').hidden === false", timeout=10_000
    )
    models = api(live_server, "/api/admin/iphone-models", key=staff_key)
    assert "iphone-cu" not in {model["model_code"] for model in models}


def test_admin_page_unauthenticated_shows_nothing_sensitive(page, live_server, staff_key):
    """Mở trang quản trị với khoá SAI: không dòng dữ liệu nào được hiện."""
    create_gift(live_server, full_name="Khách Bí Mật")

    page.goto(live_server + "/admin-leads.html", wait_until="load")
    page.fill("#staffKey", "khoa-sai-hoan-toan")
    page.click("#searchBtn")

    page.wait_for_function(
        "() => document.getElementById('errorBox').hidden === false", timeout=10_000
    )
    assert "Khách Bí Mật" not in page.content()
    assert "0912345678" not in page.content()
    assert page.locator("#leadRows").inner_text().strip() in {"", "Chưa tải dữ liệu."}


__all__ = ["api", "create_gift", "html_fingerprints"]
