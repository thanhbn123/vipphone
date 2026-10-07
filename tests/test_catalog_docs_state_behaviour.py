"""V7 + V11 — HÀNH VI CHƯA GHI THÌ PHẢI GHI RA.

Cùng loại với V2/V3 (`tests/test_catalog_docs_match_code.py`) nhưng ngược chiều:
ở kia tài liệu nói SAI điều mã đang làm, ở đây tài liệu **im lặng** về điều mã
đang làm. Im lặng cũng là một dạng sai: người đọc không phân biệt được "hệ thống
cố ý cho phép" với "hệ thống bỏ sót".

- **V7:** `categories` không có route `POST`/`PATCH`/`DELETE` nào, nhưng tài liệu
  và migration không nói vậy ⇒ người vận hành đi tìm API để tắt một category.
- **V11:** bán dưới giá nhập tạo được (`201`), nhưng §4 chỉ liệt kê 5 luật giá và
  không nhắc luật này ⇒ không biết là chủ ý hay lỗ hổng.

Rủi ro không ghi là rủi ro bị bỏ quên — nên ở đây chốt bằng phép đo.
"""

from __future__ import annotations

from app.config import REPO_ROOT

CATALOG_MD = REPO_ROOT / "docs" / "catalog.md"
MIGRATION_0007 = REPO_ROOT / "migrations" / "versions" / "0007_product_catalog.py"


def test_docs_state_that_categories_have_no_write_path():
    """V7 — `categories` không có đường GHI thì tài liệu phải NÓI RÕ cách sửa hiện tại."""
    text = CATALOG_MD.read_text(encoding="utf-8")
    assert "không có đường GHI nào" in text, (
        "docs/catalog.md phải nói rõ `categories` chỉ ĐỌC ở G14"
    )
    assert "UPDATE categories SET active = false" in text, (
        "phải ghi cách làm hiện tại bằng SQL, nếu không người đọc tưởng có route"
    )


def test_migration_comment_warns_that_categories_are_sql_only():
    """V7 — chú thích ngay tại migration, nơi người sửa bảng sẽ đọc."""
    source = (REPO_ROOT / "migrations" / "versions" / "0007_product_catalog.py").read_text(
        encoding="utf-8"
    )
    assert "KHÔNG có đường GHI nào cho `categories`" in source, (
        "migration 0007 phải cảnh báo rằng category hiện chỉ sửa được bằng SQL"
    )


def test_docs_state_the_below_cost_rule():
    """V11 — luật 'bán dưới giá nhập' phải có trong §4, kèm lý do."""
    text = CATALOG_MD.read_text(encoding="utf-8")
    assert "### 4.1" in text, "thiếu §4.1 — luật bán dưới giá nhập phải được ghi"
    section = text.split("### 4.1", 1)[1].split("\n### ", 1)[0]
    assert "HỢP LỆ" in section, "§4.1 phải nói rõ bán dưới giá nhập là ca HỢP LỆ"
    assert "xả hàng" in section, "§4.1 phải nêu lý do nghiệp vụ (xả hàng tồn)"
    assert "test_selling_below_cost_price_is_allowed" in section, (
        "§4.1 phải trỏ tới bài test đang chốt hành vi này"
    )
