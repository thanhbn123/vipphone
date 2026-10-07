"""V8 — TIỀN HIỂN THỊ PHẢI KHỚP TIỀN ĐÃ LƯU.

LỖI ĐÃ XẢY RA (đo được, không phải giả định): `assets/js/shop.js` và
`assets/js/product.js` mỗi tệp có một bản `formatMoney` chép tay dùng
`Number(value)` + `new Intl.NumberFormat("vi-VN")`. Với mặc định của `Intl`,
`"250000.10"` in ra **`250.000,1 đ`** — MẤT chữ số 0 cuối, tức là khách nhìn thấy
một mức giá KHÁC mức giá đã lưu trong DB.

VÌ SAO BỘ TEST CŨ KHÔNG BẮT ĐƯỢC: `tests/test_product_catalog.py` đo tầng API, và
tầng API trả đúng (`"250000.10"`). Lỗi nằm ở tầng hiển thị, mà tầng đó không có
test nào. Đây đúng dạng "hỏng im lặng" — không ai báo lỗi, chỉ có khách đọc sai giá.

CÁCH ĐO Ở ĐÂY: chạy `node scripts/kiem-tien-hien-thi.js`, và chốt đó
`require()` ĐÚNG tệp đang phục vụ khách (`assets/js/money.js`) — không chép lại
logic vào bộ test. Cộng thêm ba chốt tĩnh không cần `node`, để kể cả khi thiếu
`node` thì đường quay lại `Number`/`Intl` vẫn bị chặn.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.config import REPO_ROOT

MONEY_JS = REPO_ROOT / "assets" / "js" / "money.js"
SHOP_JS = REPO_ROOT / "assets" / "js" / "shop.js"
PRODUCT_JS = REPO_ROOT / "assets" / "js" / "product.js"
CHECK_SCRIPT = REPO_ROOT / "scripts" / "kiem-tien-hien-thi.js"

#: Ca sinh ra bản vá. `"250000.10"` từng hiện ra `250.000,1 đ`.
REGRESSION_CASE = '"250000.10", "VND", "250.000,10 đ"'


def _strip_comments(source: str) -> str:
    """Bỏ chú thích trước khi quét mã.

    Chính tài liệu trong các tệp này có nhắc tên `Number`/`Intl` để giải thích vì
    sao CẤM dùng chúng. Quét thô sẽ báo động giả, rồi chốt thành vô dụng —
    xem CLAUDE.md §12.1 (thứ dùng để kiểm chứng phải tự nó đáng tin).
    """
    source = re.sub(r"/\*[\s\S]*?\*/", "", source)
    return re.sub(r"(^|[^:])//.*$", r"\1", source, flags=re.MULTILINE)


def test_money_formatter_source_never_uses_float_or_intl():
    """Tiền hiển thị KHÔNG được đi qua `Number`/`parseFloat`/`Intl`."""
    code = _strip_comments(MONEY_JS.read_text(encoding="utf-8"))
    for forbidden in ("Number(", "parseFloat", "parseInt", "Intl."):
        assert forbidden not in code, (
            f"assets/js/money.js chứa {forbidden!r} — tiền là chuỗi thập phân, "
            "đổi sang số thực là mất chữ số (ca '250000.10' → '250.000,1')."
        )


def test_pages_do_not_keep_their_own_copy_of_formatMoney():
    """Hai trang phải dùng CHUNG một bản, không mỗi trang một bản chép tay."""
    for path in (SHOP_JS, PRODUCT_JS):
        code = _strip_comments(path.read_text(encoding="utf-8"))
        assert "Number(" not in code and "Intl." not in code, (
            f"{path.name} tự định dạng tiền bằng số thực — phải gọi `window.VPMoney`."
        )
        assert "window.VPMoney" in code, (
            f"{path.name} không dùng `window.VPMoney` — tiền sẽ lệch giữa hai trang."
        )
        # Không được khai lại hàm: hai bản là hai bản sẽ lệch nhau.
        assert not re.search(r"function\s+formatMoney\s*\(", code), (
            f"{path.name} khai lại `formatMoney` — bản thứ hai sẽ lệch khỏi bản chung."
        )


def test_money_js_is_loaded_before_each_page_script():
    """`money.js` phải nạp TRƯỚC script của trang, nếu không `window.VPMoney` là `undefined`."""
    for page, own_script in (
        ("shop.html", "/assets/js/shop.js"),
        ("product.html", "/assets/js/product.js"),
    ):
        html = (REPO_ROOT / page).read_text(encoding="utf-8")
        assert 'src="/assets/js/money.js"' in html, f"{page} thiếu thẻ nạp /assets/js/money.js"
        assert html.index("/assets/js/money.js") < html.index(own_script), (
            f"{page} nạp money.js SAU {own_script} — trang sẽ vỡ."
        )


def test_money_check_script_covers_the_regression_case():
    """Chốt phải thật sự chứa ca sinh ra bản vá — nếu không nó không chặn được gì."""
    source = CHECK_SCRIPT.read_text(encoding="utf-8")
    assert REGRESSION_CASE in source, (
        "scripts/kiem-tien-hien-thi.js thiếu ca '250000.10' → phải hiện '250.000,10 đ'."
    )


def test_formatMoney_outputs_two_decimals_from_decimal_strings():
    """Chạy chốt node trên ĐÚNG tệp đang phục vụ khách.

    Nếu máy không có `node`, bài này BỎ QUA có nêu lý do — chốt cứng nằm ở job CI
    `Validate static frontend` (bước `node scripts/kiem-tien-hien-thi.js`), nơi
    `node` chắc chắn có. Ba chốt tĩnh ở trên vẫn chạy đủ dù thiếu `node`.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("không có `node` trong PATH — chốt cứng ở job CI 'Validate static frontend'")

    completed = subprocess.run(
        [node, str(CHECK_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    assert completed.returncode == 0, "TIỀN HIỂN THỊ SAI:\n" + completed.stdout + completed.stderr
    # Đo lại đúng ca sinh ra bản vá, bằng chính tệp phục vụ khách.
    direct = subprocess.run(
        [
            node,
            "-e",
            (
                f"const m = require({str(MONEY_JS)!r});"
                'console.log(m.formatMoney("250000.10", "VND"));'
            ),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    assert direct.returncode == 0, direct.stderr
    assert direct.stdout.strip() == "250.000,10 đ", (
        f"nhận {direct.stdout.strip()!r}, phải là '250.000,10 đ' (đủ 2 chữ số thập phân)"
    )


def test_money_module_paths_exist():
    """Chốt đường dẫn để bài test không im lặng bỏ qua khi tệp bị đổi tên."""
    for path in (MONEY_JS, SHOP_JS, PRODUCT_JS, CHECK_SCRIPT):
        assert Path(path).is_file(), f"thiếu tệp: {path}"
