"""API quản trị lead (G05): xác thực, IDOR, lọc, phân trang, export CSV.

NGUYÊN TẮC ĐO LƯỜNG CỦA FILE NÀY (MASTER_STATUS §17, ca 8):

Mỗi test an ninh ở đây đều đã được kiểm bằng **đối chứng âm** — phá đúng thứ nó
định bảo vệ, chạy lại, và xác nhận nó **FAIL**. Test nào không FAIL khi phá thì
không kiểm gì cả. Kết quả đo ghi ở `docs/MASTER_STATUS.md` §20.

Vì vậy các test dưới đây cố ý **đo hành vi** (gọi HTTP, đọc byte trả về, đọc
`pg_stat_activity` khi cần) chứ không grep nội dung file nguồn.
"""

from __future__ import annotations

import csv
import io
import uuid

import pytest

from app.models import Lead

pytestmark = pytest.mark.integration

STAFF_HEADERS = {"X-Staff-Key": "staff-key-for-tests-only"}

PII_NAME = "Nguyễn Văn A"
PII_PHONE = "0912345678"


def create_lead(client, payload, **overrides) -> dict:
    body = {**payload, **overrides}
    response = client.post("/api/leads", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def make_many(client, payload, count: int, *, phone_prefix: str = "091234") -> list[dict]:
    """Tạo `count` lead khác số điện thoại (chính sách chống trùng theo SĐT + model)."""
    created = []
    for index in range(count):
        phone = f"{phone_prefix}{index:04d}"
        created.append(create_lead(client, payload, phone=phone))
    return created


# ==========================================================================
# 1. RANH GIỚI XÁC THỰC + IDOR
# ==========================================================================


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/admin/leads"),
        ("get", "/api/admin/leads.csv"),
        ("get", f"/api/admin/leads/{uuid.uuid4()}"),
        ("get", "/api/admin/iphone-models"),
    ],
)
def test_admin_read_routes_require_staff_auth(client, method, path):
    """Không có khoá ⇒ 401 cho MỌI route quản trị, kể cả route chỉ đọc."""
    response = getattr(client, method)(path)
    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "STAFF_UNAUTHORIZED"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/admin/iphone-models"),
        ("patch", "/api/admin/iphone-models/iphone-16-pro-max"),
    ],
)
def test_admin_write_routes_require_staff_auth(client, method, path):
    response = getattr(client, method)(path, json={"display_name": "X"})
    assert response.status_code == 401, response.text


def test_admin_rejects_wrong_key(client, valid_lead_payload):
    create_lead(client, valid_lead_payload)
    for path in ("/api/admin/leads", "/api/admin/leads.csv"):
        response = client.get(path, headers={"X-Staff-Key": "khong-phai-khoa"})
        assert response.status_code == 401, path


def test_admin_routes_fail_closed_when_staff_auth_not_configured(
    client, valid_lead_payload, monkeypatch
):
    """Chưa cấu hình `STAFF_API_KEYS` ⇒ ĐÓNG (503). Tuyệt đối không mở toang."""
    from app import security

    created = create_lead(client, valid_lead_payload)
    monkeypatch.setattr(security.settings, "staff_api_keys", "")

    for path in (
        "/api/admin/leads",
        "/api/admin/leads.csv",
        f"/api/admin/leads/{created['lead_id']}",
        "/api/admin/iphone-models",
    ):
        response = client.get(path, headers=STAFF_HEADERS)
        assert response.status_code == 503, path
        assert response.json()["error"]["code"] == "STAFF_AUTH_NOT_CONFIGURED"


def test_admin_unauthenticated_response_leaks_no_lead_data(client, valid_lead_payload):
    """IDOR: thiếu khoá thì KHÔNG được rò bất kỳ trường nào của lead."""
    create_lead(client, valid_lead_payload)

    for headers in ({}, {"X-Staff-Key": "sai"}, {"Authorization": "Bearer sai"}):
        response = client.get("/api/admin/leads", headers=headers)
        assert response.status_code == 401
        raw = response.text
        assert PII_NAME not in raw
        assert PII_PHONE not in raw
        assert "gift_code" not in raw
        assert "items" not in raw

        csv_response = client.get("/api/admin/leads.csv", headers=headers)
        assert csv_response.status_code == 401
        assert PII_NAME not in csv_response.text
        assert PII_PHONE not in csv_response.text


def test_admin_detail_without_auth_does_not_reveal_existence(client, valid_lead_payload):
    """Không có khoá: lead CÓ và lead KHÔNG có phải trả CÙNG kết quả (401)."""
    created = create_lead(client, valid_lead_payload)

    known = client.get(f"/api/admin/leads/{created['lead_id']}")
    unknown = client.get(f"/api/admin/leads/{uuid.uuid4()}")
    assert known.status_code == unknown.status_code == 401
    assert known.text == unknown.text


def test_admin_leads_csv_route_is_not_shadowed_by_detail_route(client, staff_headers):
    """`/leads.csv` phải khớp route CSV, KHÔNG bị `{lead_id}` nuốt thành 422.

    Đây là lỗi im lặng về nghiệp vụ: route CSV "biến mất" mà không có cảnh báo.
    """
    response = client.get("/api/admin/leads.csv", headers=staff_headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")


def test_admin_detail_is_not_publicly_reachable_by_gift_code(
    client, valid_lead_payload, staff_headers
):
    """`lead_id` là UUID, không nhận `gift_code` — không có đường tra chéo."""
    created = create_lead(client, valid_lead_payload)
    response = client.get(f"/api/admin/leads/{created['gift_code']}", headers=staff_headers)
    assert response.status_code == 404


# ==========================================================================
# 2. PHÂN TRANG + SẮP XẾP
# ==========================================================================


def test_admin_list_returns_total_and_page_metadata(client, valid_lead_payload, staff_headers):
    make_many(client, valid_lead_payload, 5)

    body = client.get("/api/admin/leads?page=1&page_size=2", headers=staff_headers).json()
    assert body["total"] == 5
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2


def test_admin_list_orders_newest_first(client, valid_lead_payload, staff_headers):
    created = make_many(client, valid_lead_payload, 4)

    body = client.get("/api/admin/leads?page_size=10", headers=staff_headers).json()
    codes = [item["gift_code"] for item in body["items"]]

    assert codes == list(reversed([item["gift_code"] for item in created]))


def test_admin_list_pages_do_not_repeat_or_skip(client, valid_lead_payload, staff_headers):
    """Ghép mọi trang (page_size=2) phải phủ ĐÚNG tập lead, không lặp, không sót."""
    created = make_many(client, valid_lead_payload, 5)
    expected = {item["gift_code"] for item in created}

    seen: list[str] = []
    for page in (1, 2, 3):
        body = client.get(f"/api/admin/leads?page={page}&page_size=2", headers=staff_headers).json()
        seen.extend(item["gift_code"] for item in body["items"])

    assert len(seen) == len(set(seen)), "có lead xuất hiện ở hai trang"
    assert set(seen) == expected


@pytest.mark.parametrize("page_size", [0, -1, 201, 10_000])
def test_admin_page_size_has_a_hard_ceiling(client, staff_headers, page_size):
    """Trần `page_size` ép bằng 422 — KHÔNG lặng lẽ cắt xuống.

    Cắt im lặng nguy hiểm hơn từ chối: client tưởng đã lấy đủ số dòng nó xin.
    """
    response = client.get(f"/api/admin/leads?page_size={page_size}", headers=staff_headers)
    assert response.status_code == 422, response.text


def test_admin_page_size_at_the_ceiling_is_accepted(client, staff_headers):
    from app.services.admin_leads import PAGE_SIZE_MAX

    response = client.get(f"/api/admin/leads?page_size={PAGE_SIZE_MAX}", headers=staff_headers)
    assert response.status_code == 200
    assert response.json()["page_size"] == PAGE_SIZE_MAX


@pytest.mark.parametrize("page", [0, -3])
def test_admin_page_must_be_positive(client, staff_headers, page):
    assert client.get(f"/api/admin/leads?page={page}", headers=staff_headers).status_code == 422


def test_admin_page_beyond_the_end_returns_empty_not_error(
    client, valid_lead_payload, staff_headers
):
    make_many(client, valid_lead_payload, 2)
    body = client.get("/api/admin/leads?page=99&page_size=10", headers=staff_headers).json()
    assert body["items"] == []
    assert body["total"] == 2


# ==========================================================================
# 3. BỘ LỌC
# ==========================================================================


def test_filter_by_phone_matches_partially(client, valid_lead_payload, staff_headers):
    create_lead(client, valid_lead_payload, phone="0912345678")
    create_lead(client, valid_lead_payload, phone="0987654321")

    body = client.get("/api/admin/leads?phone=0912", headers=staff_headers).json()
    assert body["total"] == 1
    assert body["items"][0]["phone"] == "0912345678"

    # Gõ có khoảng trắng cũng phải ra cùng kết quả.
    spaced = client.get("/api/admin/leads?phone=0912%20345", headers=staff_headers).json()
    assert spaced["total"] == 1


def test_filter_by_phone_does_not_treat_input_as_wildcard(
    client, valid_lead_payload, staff_headers
):
    """`%` và `_` của người dùng KHÔNG được thành ký tự đại diện của LIKE.

    Không escape thì gõ `%` là nhận về toàn bộ bảng — bộ lọc "tìm một phần"
    lặng lẽ biến thành "không lọc gì".

    GHI CHÚ ĐO LƯỜNG (đã đo, không suy đoán): có HAI lớp cùng chặn ca này —
    (1) `normalize_phone_digits` bỏ mọi ký tự không phải chữ số, (2) `escape_like`
    escape `%`/`_` trước khi dựng mẫu LIKE. Đối chứng âm cho thấy bỏ RIÊNG lớp (2)
    thì test vẫn PASS (lớp 1 đã chặn), nên đã đo thêm một ca nữa: bỏ lớp (1) mà
    giữ lớp (2) → vẫn PASS (chứng minh `escape_like` một mình đủ), và bỏ CẢ HAI →
    test này FAIL. Xem MASTER_STATUS §20, NC8a/NC8b.
    """
    make_many(client, valid_lead_payload, 3)

    for probe in ("%", "_%", "%%"):
        body = client.get(f"/api/admin/leads?phone={probe}", headers=staff_headers).json()
        assert body["total"] == 0, f"mẫu {probe!r} khớp toàn bộ bảng"


def test_filter_by_phone_without_digits_matches_nothing(client, valid_lead_payload, staff_headers):
    make_many(client, valid_lead_payload, 3)
    body = client.get("/api/admin/leads?phone=abc", headers=staff_headers).json()
    assert body["total"] == 0


def test_filter_by_model_source_and_status(client, valid_lead_payload, staff_headers):
    create_lead(client, valid_lead_payload, source="bni")
    create_lead(client, valid_lead_payload, phone="0911111111", source="facebook")

    assert client.get("/api/admin/leads?source=bni", headers=staff_headers).json()["total"] == 1
    assert client.get("/api/admin/leads?source=tiktok", headers=staff_headers).json()["total"] == 0

    # Lọc theo `model_code` (UI gửi) phải tra ra tên hiển thị đã lưu.
    by_code = client.get(
        "/api/admin/leads?iphone_model=iphone-16-pro-max", headers=staff_headers
    ).json()
    assert by_code["total"] == 2

    # Và lọc theo tên hiển thị cũng phải ra đúng kết quả đó.
    by_name = client.get(
        "/api/admin/leads?iphone_model=iPhone%2016%20Pro%20Max", headers=staff_headers
    ).json()
    assert by_name["total"] == 2

    assert (
        client.get("/api/admin/leads?gift_status=NEW", headers=staff_headers).json()["total"] == 2
    )
    assert (
        client.get("/api/admin/leads?gift_status=REDEEMED", headers=staff_headers).json()["total"]
        == 0
    )


def test_filter_by_gift_status_is_case_insensitive_but_validated(client, staff_headers):
    assert client.get("/api/admin/leads?gift_status=new", headers=staff_headers).status_code == 200
    bad = client.get("/api/admin/leads?gift_status=khong-ton-tai", headers=staff_headers)
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_FAILED"


def test_filter_by_date_range(client, valid_lead_payload, staff_headers, db):
    """Lọc theo ngày: đẩy một lead về quá khứ rồi đo ranh giới hai đầu."""
    import datetime as dt

    created = create_lead(client, valid_lead_payload)
    make_many(client, valid_lead_payload, 2)

    # Đẩy lead đầu tiên về 2020-05-05 12:00 UTC, hai lead còn lại ở hiện tại.
    db.execute(
        Lead.__table__.update()
        .where(Lead.lead_id == uuid.UUID(created["lead_id"]))
        .values(created_at=dt.datetime(2020, 5, 5, 12, 0, tzinfo=dt.UTC))
    )
    db.commit()

    only_old = client.get(
        "/api/admin/leads?created_from=2020-05-05&created_to=2020-05-05", headers=staff_headers
    ).json()
    assert only_old["total"] == 1, "lọc trọn một ngày phải bắt được lead trong ngày đó"

    before = client.get("/api/admin/leads?created_to=2020-05-04", headers=staff_headers).json()
    assert before["total"] == 0

    after = client.get("/api/admin/leads?created_from=2021-01-01", headers=staff_headers).json()
    assert after["total"] == 2


def test_filter_date_range_reversed_is_rejected(client, staff_headers):
    response = client.get(
        "/api/admin/leads?created_from=2024-01-10&created_to=2024-01-01", headers=staff_headers
    )
    assert response.status_code == 422


def test_filter_date_must_be_iso(client, staff_headers):
    assert (
        client.get("/api/admin/leads?created_from=10/01/2024", headers=staff_headers).status_code
        == 422
    )


# ==========================================================================
# 4. CHI TIẾT
# ==========================================================================


def test_admin_detail_returns_full_record(client, valid_lead_payload, staff_headers):
    created = create_lead(client, valid_lead_payload)

    body = client.get(f"/api/admin/leads/{created['lead_id']}", headers=staff_headers).json()
    assert body["lead_id"] == created["lead_id"]
    assert body["phone"] == PII_PHONE  # khu vực quản trị: đủ trường, có xác thực
    assert body["company_name"] == "Công ty TNHH ABC"
    assert body["bni_chapter"] == "BNI Growth"
    assert body["source"] == "bni"
    assert body["consent"] is True


def test_admin_detail_unknown_id_returns_404(client, staff_headers):
    response = client.get(f"/api/admin/leads/{uuid.uuid4()}", headers=staff_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "LEAD_NOT_FOUND"


def test_admin_detail_malformed_id_returns_404_not_500(client, staff_headers):
    response = client.get("/api/admin/leads/khong-phai-uuid", headers=staff_headers)
    assert response.status_code == 404


# ==========================================================================
# 5. EXPORT CSV
# ==========================================================================


def parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_csv_has_stable_header(client, staff_headers):
    from app.services.admin_leads import CSV_COLUMNS

    response = client.get("/api/admin/leads.csv", headers=staff_headers)
    assert response.status_code == 200
    header = response.text.splitlines()[0]
    assert header.split(",")[: len(CSV_COLUMNS)] == list(CSV_COLUMNS)
    assert "attachment" in response.headers["content-disposition"]


def test_csv_uses_the_same_filters_as_the_list(client, valid_lead_payload, staff_headers):
    """CSV phải cùng bộ lọc với danh sách — đo bằng SỐ DÒNG, không bằng lời hứa."""
    create_lead(client, valid_lead_payload, phone="0912345678")
    create_lead(client, valid_lead_payload, phone="0987654321")
    create_lead(client, valid_lead_payload, phone="0912000000")

    for query in ("", "?phone=0912", "?source=bni", "?gift_status=NEW", "?phone=0912&source=bni"):
        listed = client.get(f"/api/admin/leads{query}", headers=staff_headers).json()
        exported = parse_csv(client.get(f"/api/admin/leads.csv{query}", headers=staff_headers).text)
        assert len(exported) == listed["total"], f"lệch ở bộ lọc {query!r}"

    filtered = parse_csv(client.get("/api/admin/leads.csv?phone=0912", headers=staff_headers).text)
    assert {row["phone"] for row in filtered} == {"0912345678", "0912000000"}


CSV_INJECTION_PAYLOADS = [
    "=cmd|' /c calc'!A0",
    "=1+1",
    "+1+1",
    "-1+1",
    "@SUM(A1)",
    '=HYPERLINK("http://evil.example")',
]


@pytest.mark.parametrize("payload", CSV_INJECTION_PAYLOADS)
def test_csv_blocks_formula_injection_in_customer_name(
    client, valid_lead_payload, staff_headers, payload
):
    """Ô bắt đầu bằng `=`, `+`, `-`, `@` phải bị VÔ HIỆU HOÁ trong file export.

    Đây là thực thi mã phía người mở file, không phải lỗi hiển thị.
    """
    create_lead(client, valid_lead_payload, full_name=payload)

    rows = parse_csv(client.get("/api/admin/leads.csv", headers=staff_headers).text)
    assert len(rows) == 1
    name = rows[0]["full_name"]

    assert name.startswith("'"), f"ô {name!r} không được vô hiệu hoá"
    assert name == "'" + payload


def test_csv_blocks_formula_injection_through_other_text_columns(
    client, valid_lead_payload, staff_headers
):
    create_lead(
        client,
        valid_lead_payload,
        company_name="=1+1",
        bni_chapter="+SUM(A1)",
        referrer_name="@evil",
    )
    rows = parse_csv(client.get("/api/admin/leads.csv", headers=staff_headers).text)
    assert rows[0]["company_name"] == "'=1+1"
    assert rows[0]["bni_chapter"] == "'+SUM(A1)"
    assert rows[0]["referrer_name"] == "'@evil"


def test_csv_blocks_leading_tab_and_cr_reachable_only_from_stored_data(
    client, db, staff_headers, valid_lead_payload
):
    """TAB/CR ở ĐẦU ô: API công khai không nhận (bị strip/validate), nhưng dữ liệu
    ĐÃ NẰM TRONG BẢNG (nhập từ script, migration, sửa tay) vẫn phải được chặn khi
    export. Đây là lớp phòng thủ ở đầu RA, không phụ thuộc đầu vào.
    """
    import uuid as uuid_mod

    db.add(
        Lead(
            lead_id=uuid_mod.uuid4(),
            gift_code="VIP-26-TAB001",
            full_name="\t=cmd",
            phone="0900000001",
            iphone_model="iPhone 16 Pro Max",
            iphone_year=2024,
            case_color="\r=1+1",
            consent=True,
            gift_status="NEW",
        )
    )
    db.commit()

    rows = parse_csv(client.get("/api/admin/leads.csv", headers=staff_headers).text)
    assert len(rows) == 1
    assert rows[0]["full_name"].startswith("'"), rows[0]["full_name"]
    assert rows[0]["case_color"].startswith("'"), rows[0]["case_color"]


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_sanitize_csv_cell_covers_every_dangerous_prefix(prefix):
    """Đo trực tiếp hàm, phủ ĐỦ sáu tiền tố nguy hiểm (kể cả tab và CR)."""
    from app.services.admin_leads import sanitize_csv_cell

    assert sanitize_csv_cell(prefix + "nguy hiem") == "'" + prefix + "nguy hiem"
    # Ô bình thường KHÔNG được thêm dấu nháy — nếu thêm hết thì file bị bẩn.
    assert sanitize_csv_cell("Nguyễn Văn A") == "Nguyễn Văn A"
    assert sanitize_csv_cell(None) == ""
    assert sanitize_csv_cell(2024) == "2024"


def test_csv_row_cap_truncates_and_reports_it(
    client, valid_lead_payload, staff_headers, monkeypatch
):
    """Trần số dòng phải được ÉP và phải được BÁO, không cắt im lặng.

    Hạ trần xuống 2 qua module (không import hằng số theo giá trị) để đo đúng
    nhánh chạm trần mà không phải nạp 5.001 dòng.
    """
    from app.services import admin_leads as service

    make_many(client, valid_lead_payload, 5)
    monkeypatch.setattr(service, "CSV_MAX_ROWS", 2)

    response = client.get("/api/admin/leads.csv", headers=staff_headers)
    rows = parse_csv(response.text)

    assert len(rows) == 2, "trần số dòng không được ép"
    assert response.headers["X-VIPPHONE-CSV-Truncated"] == "true"
    assert response.headers["X-VIPPHONE-CSV-Rows"] == "2"


def test_csv_below_the_cap_is_not_marked_truncated(client, valid_lead_payload, staff_headers):
    make_many(client, valid_lead_payload, 3)
    response = client.get("/api/admin/leads.csv", headers=staff_headers)
    assert len(parse_csv(response.text)) == 3
    assert response.headers["X-VIPPHONE-CSV-Truncated"] == "false"


def test_csv_escapes_commas_and_quotes_without_breaking_rows(
    client, valid_lead_payload, staff_headers
):
    """Tên có dấu phẩy/nháy kép không được làm vỡ cấu trúc file."""
    create_lead(client, valid_lead_payload, full_name='Nguyễn "A", B')

    rows = parse_csv(client.get("/api/admin/leads.csv", headers=staff_headers).text)
    assert len(rows) == 1
    assert rows[0]["full_name"] == 'Nguyễn "A", B'


def test_csv_neutralizes_newline_in_stored_text(client, db, staff_headers):
    """Xuống dòng trong dữ liệu không được tạo thêm dòng trong CSV."""
    import uuid as uuid_mod

    db.add(
        Lead(
            lead_id=uuid_mod.uuid4(),
            gift_code="VIP-26-NL0001",
            full_name="Dòng một\nDòng hai",
            phone="0900000002",
            iphone_model="iPhone 16 Pro Max",
            iphone_year=2024,
            case_color="Đen",
            consent=True,
            gift_status="NEW",
        )
    )
    db.commit()

    rows = parse_csv(client.get("/api/admin/leads.csv", headers=staff_headers).text)
    assert len(rows) == 1
    assert rows[0]["full_name"] == "Dòng một\nDòng hai"
