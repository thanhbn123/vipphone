"""V2 + V3 — TÀI LIỆU `docs/catalog.md` PHẢI KHỚP MÃ.

VÌ SAO CÓ TỆP NÀY: hai phát hiện của vòng phản biện đều thuộc **cùng một loại** —
tài liệu nói một đằng, mã làm một nẻo, và **không có gì báo lỗi**:

- **V2:** `docs/catalog.md` gọi `public_product_query` — hàm **KHÔNG tồn tại**.
  Tên thật là `product_query` + `ProductFilters.active_only`. Người đọc tài liệu
  đi tìm hàm đó trong mã sẽ không thấy, và không biết mình đọc nhầm hay mã thiếu.
- **V3:** `docs/catalog.md` §6.2 khai vị từ `dc.device_brand = :brand`, mã
  (`_compatible_exists`) **chỉ** so `device_model_code`.

Sửa chữ trong tài liệu là chưa đủ — bản sau sẽ lệch lại y như vậy (§12.2: một cấu
trúc hỏng lần thứ hai thì đổi cấu trúc). Nên ở đây biến hai lời khẳng định đó
thành **phép đo chạy được**, buộc tài liệu và mã phải đổi cùng nhau.
"""

from __future__ import annotations

import inspect
import re

import pytest

from app.config import REPO_ROOT
from app.services import catalog

CATALOG_MD = REPO_ROOT / "docs" / "catalog.md"
TEST_CATALOG_PY = REPO_ROOT / "tests" / "test_product_catalog.py"

#: Tên hàm tài liệu được phép nhắc tới ở §5.4/§5.5 — phải có THẬT trong service.
NAMED_IN_DOCS = (
    "product_query",
    "list_categories",
    "load_variants",
    "load_compatibility",
    "serialize_public",
    "serialize_admin",
    "create_variant",
    "patch_variant",
)


def test_docs_never_name_a_function_that_does_not_exist():
    """V2 — `public_product_query` không được đóng vai tên hàm THẬT.

    Tài liệu viết tên hàm để người đọc tra thẳng vào mã. Một cái tên không tồn tại
    biến việc tra cứu thành ngõ cụt, mà không có gì báo lỗi.

    Cho phép ĐÚNG một cách nhắc: nhắc để nói nó SAI (`không phải ...`). Đó là thông
    tin có ích — người từng đọc bản tài liệu cũ cần biết mình đã đọc nhầm. Nhưng
    bài test chỉ chấp nhận khi dòng đó tự khai nó sai.
    """
    test_text = TEST_CATALOG_PY.read_text(encoding="utf-8")
    assert "public_product_query" not in test_text, (
        "tests/test_product_catalog.py nhắc `public_product_query` — tên này KHÔNG tồn tại"
    )

    for number, line in enumerate(CATALOG_MD.read_text(encoding="utf-8").splitlines(), 1):
        if "public_product_query" in line:
            assert "không phải" in line, (
                f"docs/catalog.md:{number} nhắc `public_product_query` mà KHÔNG nói rõ nó sai — "
                "người đọc sẽ tưởng đây là tên hàm thật. Tên thật: `product_query` + "
                "`ProductFilters.active_only` (§5.4)."
            )


def test_docs_named_functions_really_exist_in_the_service():
    """Vế còn lại của V2: tên nào tài liệu nhắc thì phải tra được trong mã."""
    for name in NAMED_IN_DOCS:
        assert hasattr(catalog, name), (
            f"tài liệu nhắc `{name}` nhưng `app.services.catalog` không có tên đó"
        )


def _sql_blocks_about_compatibility() -> list[str]:
    """Các khối ```sql trong `docs/catalog.md` nói về `device_compatibility`."""
    text = CATALOG_MD.read_text(encoding="utf-8")
    blocks = re.findall(r"```sql\n(.*?)```", text, flags=re.DOTALL)
    return [block for block in blocks if "device_compatibility" in block]


def test_docs_compatibility_sql_matches_the_code():
    """V3 — vị từ trong tài liệu và vị từ trong mã phải nói CÙNG một chuyện.

    Cặp phép đo: mã có lọc `device_brand` hay không, và khối SQL của tài liệu có
    nhắc `device_brand` hay không. Hai vế phải BẰNG NHAU. Ai đổi một bên mà quên
    bên kia sẽ làm bài này ĐỎ — thay vì để hai bản lệch nhau im lặng như trước.
    """
    if not _sql_blocks_about_compatibility():
        pytest.fail(
            "docs/catalog.md không còn khối ```sql nào về device_compatibility — "
            "bài test này đang đo vào chỗ rỗng, xem lại §6.2"
        )

    code_filters_brand = "device_brand" in inspect.getsource(catalog._compatible_exists)
    docs_mention_brand = any("device_brand" in block for block in _sql_blocks_about_compatibility())

    assert code_filters_brand == docs_mention_brand, (
        "TÀI LIỆU VÀ MÃ LỆCH NHAU: "
        f"mã lọc `device_brand` = {code_filters_brand}, "
        f"khối SQL của tài liệu nhắc `device_brand` = {docs_mention_brand}. "
        "Sửa một bên thì phải sửa bên kia, và ghi rõ ở §6.4."
    )

    # Vế tích cực: khoá join THẬT SỰ dùng phải có mặt trong tài liệu.
    assert all("device_model_code" in block for block in _sql_blocks_about_compatibility()), (
        "khối SQL của tài liệu phải nói rõ khoá join là `device_model_code`"
    )


def test_docs_state_the_known_brand_limitation():
    """V3 không được 'sửa tài liệu cho im': giới hạn còn lại phải được GHI RA.

    Rủi ro không ghi là rủi ro bị bỏ quên. Nếu ai xoá §6.4 để tài liệu trông sạch,
    bài này ĐỎ.
    """
    text = CATALOG_MD.read_text(encoding="utf-8")
    assert "### 6.4" in text, "thiếu §6.4 — giới hạn lọc theo brand phải được ghi rõ"
    section = text.split("### 6.4", 1)[1].split("\n### ", 1)[0]
    for needle in ("device_brand", "UNIQUE", "việc mở"):
        assert needle in section, f"§6.4 thiếu ý {needle!r}"
