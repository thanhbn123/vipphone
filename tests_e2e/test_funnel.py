"""E2E luồng chính VIP PHONE — trình duyệt thật, API thật, PostgreSQL thật.

Mỗi test ở đây phải **phân biệt được**: nếu phá thứ nó định bảo vệ thì nó phải FAIL.
Xem `docs/MASTER_STATUS.md` §17 (ca 8) — một test PASS không có nghĩa là nó kiểm được gì.
"""

from __future__ import annotations

import io
import json
import re

import pytest
import zxingcpp
from PIL import Image
from sqlalchemy import create_engine, text

from tests_e2e.conftest import recorded_events

pytestmark = [pytest.mark.e2e]

GIFT_CODE_RE = re.compile(r"^VIP-\d{2}-[A-Z0-9]{6}$")


def query(database_url: str, sql: str, **params):
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as conn:
            return conn.execute(text(sql), params).all()
    finally:
        engine.dispose()


def fill_lead_form(
    page, *, name="Nguyễn Văn A", phone="0912345678", model="iphone-16-pro-max", color="Đen"
):
    page.click("#full_name")
    page.fill("#full_name", name)
    page.fill("#phone", phone)
    page.select_option("#iphone_model", model)
    page.select_option("#case_color", color)
    page.check("#consent")


def submit_and_wait(page):
    page.click("#submitBtn")
    page.wait_for_url("**/success.html", timeout=20_000)
    return page.inner_text("#giftCode").strip()


@pytest.fixture
def page(funnel_page):
    """Bí danh CỤC BỘ trong module này: dùng bộ ghi event bền của `funnel_page`.

    Fixture khai trong chính module test sẽ ĐÈ fixture cùng tên ở `conftest.py`
    — nhưng chỉ cho module này. Nhờ vậy bộ funnel đọc được event sống sót qua
    điều hướng, mà fixture `page` của gate (có hứng lỗi console) KHÔNG bị đụng tới.
    """
    return funnel_page


# ------------------------------------------------------------------- helpers
def open_landing(page, base_url: str, query_string: str = ""):
    """Mở landing rồi CHỜ danh mục tải xong.

    KHÔNG dùng `wait_until="networkidle"`: Playwright khuyến nghị tránh vì nó
    treo khi trang còn request nền. Nhưng chỉ `wait_until="load"` là CHƯA ĐỦ —
    danh mục được nạp bằng `fetch` SAU khi trang load, nên phải chờ đúng điều
    kiện giao diện. Chờ đúng điều kiện thì tất định, và KHÔNG che lỗi: nếu ứng
    dụng thật sự treo thì phép chờ này vẫn FAIL.
    """
    page.goto(f"{base_url}/{query_string}", wait_until="load")
    page.wait_for_function(
        # `option[value!=""]` la cu phap JQUERY, khong phai CSS -> dung se
        # nem SyntaxError. Loc bang JS cho chac.
        "() => Array.from(document.querySelectorAll('#iphone_model option'))"
        ".filter(o => o.value).length > 0",
        timeout=20_000,
    )
    return page


def wait_for_result(page):
    """Chờ trang nhân viên tới TRẠNG THÁI CUỐI, không phải trạng thái đang tải.

    ⚠️  BẪY ĐÃ DÍNH: bản đầu chỉ chờ `#redeemResult` khác rỗng. Nhưng thứ đầu
    tiên trang hiện ra là dòng "Đang tra cứu…", nên phép chờ thoả NGAY và test
    đọc nhầm trạng thái trung gian — 3 test FAIL vì lý do không liên quan tới
    sản phẩm. Phải chờ tới khi hết trạng thái đang tải.
    """
    page.wait_for_function(
        "() => { const el = document.getElementById('redeemResult');"
        " if (!el) return false;"
        " const t = el.innerText.trim();"
        " return t.length > 0 && !t.includes('Đang tra cứu'); }",
        timeout=20_000,
    )


def open_redeem(page, base_url: str, code=None, key=None):
    """Mở trang nhân viên và CHỜ kết quả tra cứu hiện ra (nếu có mã)."""
    url = f"{base_url}/redeem.html"
    if code:
        url += f"?code={code}"
    # Khoá nhân viên phải có MẶT TRƯỚC khi trang chạy: redeem.js tự tra cứu
    # ngay khi tải nếu URL có `?code=`, và nếu lúc đó chưa có khoá thì nó nhận
    # 401 rồi KHÔNG tra lại nữa (điền khoá sau là quá muộn).
    if key is not None:
        # Dùng f-string + json.dumps để nhúng chuỗi vào JS cho an toàn
        # (không dùng %-format: ruff UP031).
        page.add_init_script(
            "try { sessionStorage.setItem('vipphone_staff_key_v1', "
            f"{json.dumps(key)}); }} catch (e) {{}}"
        )
    page.goto(url, wait_until="load")
    if code:
        wait_for_result(page)
    return page


def wait_for_redeem_outcome(page, kind: str = "ok"):
    """Chờ kết quả CUỐI của bước phát quà.

    Sau khi bấm xác nhận, `renderBox` THAY TOÀN BỘ nội dung `#redeemResult` bằng
    một hộp `.status`. Trước đó bảng chi tiết + nút "ĐANG GHI…" đã làm cho
    `innerText` khác rỗng, nên chờ "khác rỗng" sẽ đọc nhầm trạng thái trung gian.
    Chờ đúng hộp trạng thái là điều kiện phân biệt được.
    """
    page.wait_for_selector(f"#redeemResult .status.{kind}", timeout=20_000)


def lookup(page, code: str, key=None):
    """Nhập mã rồi chờ kết quả tra cứu."""
    if key is not None:
        page.fill("#staffKey", key)
    page.fill("#redeemCode", code)
    page.click("button[type=submit]")
    wait_for_result(page)


# --------------------------------------------------------------------- landing
def test_landing_emits_view_event_and_loads_catalog_from_api(page, server):
    open_landing(page, server["base_url"])

    assert "vipphone_landing_view" in recorded_events(page)

    options = page.eval_on_selector_all(
        "#iphone_model option", "els => els.map(e => e.value).filter(Boolean)"
    )
    # 28 model đúng bằng seed của migration — KHÔNG hard-code trong HTML.
    assert len(options) == 28, options
    assert options[0] == "iphone-16", options[0]
    assert page.is_enabled("#submitBtn")


def test_landing_has_no_inline_script_style_or_handler(page, server):
    """CSP nghiêm (`script-src 'self'`) sẽ chặn inline — phải không có cái nào."""
    open_landing(page, server["base_url"])
    html = page.content()

    assert "<script>" not in html
    for event in ("onclick=", "onsubmit=", "onchange=", "onload="):
        assert event not in html.lower(), event


def test_server_blocks_invalid_phone_even_if_client_is_bypassed(page, server):
    """Bỏ qua validation ở client thì SERVER vẫn phải chặn.

    Đây mới là điều đáng kiểm: validation client chỉ là tiện ích, không phải
    ranh giới an ninh.
    """
    open_landing(page, server["base_url"])

    response = page.evaluate(
        """async (base) => {
            const r = await fetch(base + '/api/leads', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    full_name: 'Kẻ Tấn Công',
                    phone: '12345',
                    iphone_model: 'iphone-16',
                    case_color: 'Đen',
                    consent: true,
                }),
            });
            return {status: r.status, body: await r.json()};
        }""",
        server["base_url"],
    )

    assert response["status"] == 422, response
    assert "phone" in response["body"]["error"]["fields"]
    assert query(server["database_url"], "SELECT count(*) FROM leads")[0][0] == 0, (
        "không được tạo lead"
    )


def test_server_ignores_client_supplied_year_and_status(page, server):
    """Không tin dữ liệu client: gửi kèm trường hệ thống phải bị TỪ CHỐI."""
    open_landing(page, server["base_url"])

    for extra in ('{"iphone_year": 1999}', '{"gift_status": "REDEEMED"}'):
        payload = (
            '{"full_name":"A","phone":"0912345678","iphone_model":"iphone-16",'
            '"case_color":"Đen","consent":true,' + extra[1:]
        )
        status = page.evaluate(
            """async ([base, body]) => {
                const r = await fetch(base + '/api/leads', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: body,
                });
                return r.status;
            }""",
            [server["base_url"], payload],
        )
        assert status == 422, (extra, status)


# ------------------------------------------------------------------ lead + QR
def test_full_funnel_creates_lead_with_canonical_phone_and_public_qr(page, server):
    base = server["base_url"]
    open_landing(
        page,
        base,
        "?src=bni&ref=MEMBER-42&utm_source=facebook&utm_medium=social"
        "&utm_campaign=camp-10&utm_content=video-a",
    )

    fill_lead_form(page, phone="+84 912 345 678")
    code = submit_and_wait(page)

    assert GIFT_CODE_RE.match(code), code
    assert "Nguyễn Văn A" in page.inner_text("#giftDetails")
    assert "iPhone 16 Pro Max" in page.inner_text("#giftDetails")

    events = recorded_events(page)
    for expected in (
        "vipphone_landing_view",
        "vipphone_form_start",
        "vipphone_lead_submit",
        "vipphone_gift_code_created",
    ):
        assert expected in events, (expected, events)

    # Database là nguồn chân lý: SĐT đã chuẩn hoá, attribution sống sót qua điều hướng.
    rows = query(
        server["database_url"],
        "SELECT phone, full_name, iphone_model, iphone_year, source, ref, "
        "utm_source, utm_medium, utm_campaign, utm_content, gift_status, consent "
        "FROM leads",
    )
    assert len(rows) == 1, rows
    assert tuple(rows[0]) == (
        "0912345678",
        "Nguyễn Văn A",
        "iPhone 16 Pro Max",
        2024,
        "bni",
        "MEMBER-42",
        "facebook",
        "social",
        "camp-10",
        "video-a",
        "NEW",
        True,
    ), tuple(rows[0])

    # QR phải là ảnh THẬT tải được, và giải mã ra ĐÚNG URL công khai.
    image = page.locator("#qr img.qr-image")
    assert image.count() == 1
    assert image.get_attribute("src") == f"/api/gifts/{code}/qr.png"

    png = page.evaluate(
        """async () => {
            const el = document.querySelector('#qr img');
            const r = await fetch(el.src);
            const buf = await r.arrayBuffer();
            return Array.from(new Uint8Array(buf));
        }"""
    )
    decoded = zxingcpp.read_barcode(Image.open(io.BytesIO(bytes(png))))
    assert decoded is not None, "ảnh QR không giải mã được"
    assert decoded.text == f"{base}/redeem?code={code}"

    # QR TUYỆT ĐỐI không chứa PII.
    for secret in ("Nguyễn Văn A", "0912345678", "Công ty", "BNI"):
        assert secret not in decoded.text, decoded.text


def test_duplicate_submission_returns_same_gift_without_second_lead(page, server):
    base = server["base_url"]

    open_landing(page, base)
    fill_lead_form(page)
    first = submit_and_wait(page)

    # Cùng khách, viết SĐT kiểu khác, cùng dòng máy.
    open_landing(page, base)
    fill_lead_form(page, phone="+84912345678")
    second = submit_and_wait(page)

    assert second == first
    assert "giữ nguyên mã quà cũ" in page.inner_text("#giftDetails")
    assert query(server["database_url"], "SELECT count(*) FROM leads")[0][0] == 1


# --------------------------------------------------------------------- redeem
def test_staff_lookup_masks_phone_and_never_returns_full_pii(page, server):
    base = server["base_url"]
    open_landing(page, base)
    fill_lead_form(page)
    code = submit_and_wait(page)

    open_redeem(page, base)
    lookup(page, code.lower(), server["staff_key"])

    body = page.inner_text("#redeemResult")
    assert "Nguyễn Văn A" in body
    assert "0912***678" in body, body
    assert "0912345678" not in body, "KHÔNG được lộ số đầy đủ"


def test_staff_lookup_requires_key(page, server):
    base = server["base_url"]
    open_landing(page, base)
    fill_lead_form(page)
    code = submit_and_wait(page)

    open_redeem(page, base)
    lookup(page, code)

    assert "khoá truy cập nhân viên hợp lệ" in page.inner_text("#redeemResult").lower()


def test_redeem_is_idempotent_and_audited_once(page, server):
    base = server["base_url"]
    open_landing(page, base)
    fill_lead_form(page)
    code = submit_and_wait(page)

    open_redeem(page, base, code=code, key=server["staff_key"])
    assert page.locator("#confirmRedeem").count() == 1
    page.click("#confirmRedeem")
    wait_for_redeem_outcome(page, "ok")
    assert "thành công" in page.inner_text("#redeemResult").lower()

    rows = query(
        server["database_url"],
        "SELECT gift_status, redeemed_at IS NOT NULL, redeemed_by FROM leads",
    )
    assert rows[0][0] == "REDEEMED"
    assert rows[0][1] is True
    assert rows[0][2].startswith("staff:")

    events = recorded_events(page)
    assert "vipphone_gift_redeemed" in events, events

    # Phát lần hai: giao diện chặn, và audit KHÔNG được ghi thêm.
    open_redeem(page, base, code=code, key=server["staff_key"])
    text = page.inner_text("#redeemResult").lower()
    assert "đã được nhận quà" in text, text
    assert page.locator("#confirmRedeem").count() == 0

    assert (
        query(
            server["database_url"],
            "SELECT count(*) FROM audit_events WHERE event_type = 'GIFT_REDEEMED'",
        )[0][0]
        == 1
    ), "chỉ được có ĐÚNG MỘT GIFT_REDEEMED"

    events = query(
        server["database_url"],
        "SELECT event_type FROM audit_events ORDER BY id",
    )
    assert [row[0] for row in events] == [
        "LEAD_CREATED",
        "GIFT_CREATED",
        "GIFT_STATUS_CHANGED",
        "GIFT_REDEEMED",
    ]


def test_redeemed_gift_cannot_be_redeemed_again_through_the_api(page, server):
    """Chặn ở GIAO DIỆN là chưa đủ — phải chặn ở API.

    Test này gọi thẳng API, bỏ qua giao diện: đây mới là ranh giới thật.
    """
    base = server["base_url"]
    open_landing(page, base)
    fill_lead_form(page)
    code = submit_and_wait(page)

    result = page.evaluate(
        """async ([base, code, key]) => {
            const call = () => fetch(`${base}/api/gifts/${code}/redeem`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-Staff-Key': key},
                body: '{}',
            }).then(r => r.json().then(b => ({status: r.status, body: b})));
            return [await call(), await call()];
        }""",
        [base, code, server["staff_key"]],
    )

    assert result[0]["body"]["already_redeemed"] is False
    assert result[1]["body"]["already_redeemed"] is True
    assert result[1]["body"]["redeemed_at"] == result[0]["body"]["redeemed_at"], (
        "redeemed_at không được đổi ở lần hai"
    )
    assert (
        query(
            server["database_url"],
            "SELECT count(*) FROM audit_events WHERE event_type = 'GIFT_REDEEMED'",
        )[0][0]
        == 1
    )


def test_redeem_rejects_cancelled_gift(page, server):
    base = server["base_url"]
    open_landing(page, base)
    fill_lead_form(page)
    code = submit_and_wait(page)

    engine = create_engine(server["database_url"], future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE leads SET gift_status = 'CANCELLED'"))
    finally:
        engine.dispose()

    status = page.evaluate(
        """async ([base, code, key]) => {
            const r = await fetch(`${base}/api/gifts/${code}/redeem`, {
                method: 'POST',
                headers: {'X-Staff-Key': key},
                body: '{}',
            });
            return r.status;
        }""",
        [base, code, server["staff_key"]],
    )
    assert status == 409


# ----------------------------------------------------------------- security hdr
def test_security_headers_present_on_pages_and_api(page, server):
    base = server["base_url"]
    open_landing(page, base)

    headers = page.evaluate(
        """async (base) => {
            const r = await fetch(base + '/api/health');
            return Object.fromEntries(r.headers.entries());
        }""",
        base,
    )
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert "script-src 'self'" in headers.get("content-security-policy", "")
    assert headers.get("cache-control") == "no-store"


# ------------------------------------------------------------------- mobile
MOBILE_VIEWPORTS = [
    ("iPhone SE", 375, 667),
    ("iPhone 14 Pro", 393, 852),
    ("Android nhỏ", 360, 640),
]


@pytest.mark.parametrize(("device", "width", "height"), MOBILE_VIEWPORTS)
def test_no_horizontal_overflow_on_mobile(mobile_context, server, device, width, height):
    """Trang không được tràn ngang ở các cỡ điện thoại phổ biến.

    Đo bằng `scrollWidth` của `documentElement` so với bề rộng khung nhìn — đây là
    phép đo thật, không phải nhìn ảnh rồi đoán.
    """
    page = mobile_context(width, height)
    try:
        for path in ("/", "/redeem.html"):
            page.goto(f"{server['base_url']}{path}", wait_until="load")
            overflow = page.evaluate(
                "() => ({scroll: document.documentElement.scrollWidth,"
                " client: document.documentElement.clientWidth})"
            )
            assert overflow["scroll"] <= overflow["client"] + 1, (
                f"{device} {width}px tràn ngang ở {path}: {overflow}"
            )
    finally:
        pass  # `mobile_context` tự đóng context


def test_lead_form_usable_on_mobile(mobile_context, server):
    """Trên điện thoại phải ĐIỀN VÀ GỬI ĐƯỢC thật, không chỉ nhìn vừa."""
    page = mobile_context(375, 667)
    try:
        page.goto(f"{server['base_url']}/", wait_until="load")
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('#iphone_model option'))"
            ".filter(o => o.value).length > 0",
            timeout=20_000,
        )
        fill_lead_form(page)
        page.click("#submitBtn")
        page.wait_for_url("**/success.html", timeout=20_000)
        assert GIFT_CODE_RE.match(page.inner_text("#giftCode").strip())

        # Mã QR phải nằm trong khung nhìn, không bị cắt.
        box = page.locator("#qr img.qr-image").bounding_box()
        assert box is not None, "không thấy ảnh QR trên điện thoại"
        assert box["x"] >= 0 and box["x"] + box["width"] <= 375 + 1, box
    finally:
        pass  # `mobile_context` tự đóng context
