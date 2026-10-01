"""Nghiệp vụ khu vực quản trị: tra cứu lead (danh sách/chi tiết) và export CSV.

QUY TẮC AN TOÀN CỦA MODULE NÀY:

1. **Xác thực là việc của router**, không phải của module này. Mọi hàm ở đây
   giả định người gọi ĐÃ qua `require_staff`. Không có hàm nào tự quyết định
   chuyện quyền — để không có hai chỗ cùng quyết một việc (mục 12.2: lọc một
   chỗ, không lọc hai chỗ).
2. **Mọi giá trị lọc đi vào SQL đều là tham số** (SQLAlchemy bind param). Ký tự
   đại diện `%` và `_` do người dùng gửi được **escape** trước khi dựng mẫu
   `LIKE`, nếu không thì "tìm một phần" biến thành "tìm tất cả".
3. **CSV phải chống formula injection**: ô bắt đầu bằng `=`, `+`, `-`, `@`,
   tab hoặc CR bị vô hiệu hoá. Xem `sanitize_csv_cell`.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..models import IphoneModel, Lead

logger = logging.getLogger("vipphone.admin")

#: Trần cứng số dòng một lần export CSV.
#:
#: Vì sao có trần: export không phân trang nên nếu không chặn, một lệnh export
#: có thể quét sạch bảng và làm treo tiến trình (một tiến trình phục vụ cả API
#: lẫn file tĩnh — xem ADR-0001 §3.2). Trần là hằng số trong mã, KHÔNG phải
#: tham số do client gửi lên, nên không nới được từ ngoài.
CSV_MAX_ROWS = 5_000

#: Trần `page_size` của API danh sách.
PAGE_SIZE_MAX = 200
PAGE_SIZE_DEFAULT = 50


@dataclass(slots=True)
class LeadFilters:
    """Bộ lọc dùng CHUNG cho danh sách và export CSV.

    Dùng chung một dataclass là cách ép "CSV cùng bộ lọc với danh sách" ở tầng
    mã: hai đường không thể lệch nhau vì cùng gọi `build_lead_query`.
    """

    phone: str | None = None
    iphone_model: str | None = None
    source: str | None = None
    gift_status: str | None = None
    created_from: dt.datetime | None = None
    #: CẬN TRÊN ĐỘC QUYỀN (`<`), không phải `<=`.
    #:
    #: Router biến ngày `created_to` thành `00:00 UTC của ngày KẾ TIẾP` rồi so
    #: bằng `<`. Nhờ vậy không phải chọn giữa `23:59:59` (mất 1 giây dữ liệu ở
    #: cuối ngày) và `23:59:59.999999` (vẫn hở nếu cột có độ chính xác cao hơn).
    created_to: dt.datetime | None = None


def escape_like(value: str) -> str:
    """Escape ký tự đại diện của `LIKE` để "khớp một phần" đúng nghĩa.

    Không escape thì người dùng gõ `%` là nhận về toàn bộ bảng — hành vi đúng
    vẫn là "khớp một phần", nhưng phần khớp lại do người dùng điều khiển.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def normalize_phone_digits(value: str) -> str:
    """Giữ lại chỉ chữ số của chuỗi tìm kiếm SĐT.

    SĐT trong bảng đã được chuẩn hoá (`0xxxxxxxxx`), nên tìm một phần cũng chỉ
    có nghĩa khi so trên chữ số. Gõ `0912 345` và `0912345` phải ra cùng kết quả.
    """
    return "".join(ch for ch in value if ch.isdigit())


def resolve_model_display_name(db: Session, value: str) -> str:
    """Nhận `model_code` HOẶC tên hiển thị, trả về giá trị lưu trong `leads`.

    `leads.iphone_model` lưu **tên hiển thị** (G02), còn UI admin chọn theo
    `model_code`. Tra danh mục trước (kể cả model đã tắt — lead cũ vẫn còn),
    không thấy thì coi như người dùng gõ thẳng tên hiển thị.
    """
    cleaned = value.strip()
    stmt = select(IphoneModel.display_name).where(IphoneModel.model_code == cleaned.lower())
    found = db.execute(stmt).scalar_one_or_none()
    return found if found is not None else cleaned


def build_lead_query(filters: LeadFilters) -> Select:
    """Dựng câu truy vấn lead từ bộ lọc. DÙNG CHUNG cho danh sách và CSV."""
    stmt = select(Lead)

    if filters.phone:
        digits = normalize_phone_digits(filters.phone)
        if digits:
            stmt = stmt.where(Lead.phone.like(f"%{escape_like(digits)}%", escape="\\"))
        else:
            # Người dùng gõ toàn ký tự không phải chữ số: không khớp gì cả.
            # Nếu bỏ qua điều kiện này thì bộ lọc "tìm theo SĐT" lặng lẽ biến
            # thành "không lọc gì" — trả về toàn bộ bảng.
            stmt = stmt.where(Lead.phone.like("", escape="\\"))

    if filters.iphone_model:
        stmt = stmt.where(Lead.iphone_model == filters.iphone_model)

    if filters.source:
        stmt = stmt.where(Lead.source == filters.source)

    if filters.gift_status:
        stmt = stmt.where(Lead.gift_status == filters.gift_status)

    if filters.created_from is not None:
        stmt = stmt.where(Lead.created_at >= filters.created_from)

    if filters.created_to is not None:
        # Cận trên ĐỘC QUYỀN — xem ghi chú ở `LeadFilters.created_to`.
        stmt = stmt.where(Lead.created_at < filters.created_to)

    return stmt


def count_leads(db: Session, filters: LeadFilters) -> int:
    """Tổng số lead khớp bộ lọc (trước khi phân trang)."""
    stmt = build_lead_query(filters).with_only_columns(func.count(Lead.id)).order_by(None)
    return int(db.execute(stmt).scalar_one())


def list_leads(db: Session, filters: LeadFilters, *, page: int, page_size: int) -> list[Lead]:
    """Một trang lead, MỚI NHẤT TRƯỚC.

    Sắp thêm `id DESC` sau `created_at DESC` để thứ tự **tất định** khi nhiều
    lead cùng mốc thời gian: thiếu nó thì hai trang liên tiếp có thể lặp hoặc
    sót hàng, và đó là lỗi im lặng.
    """
    stmt = (
        build_lead_query(filters)
        .order_by(Lead.created_at.desc(), Lead.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(db.execute(stmt).scalars().all())


def get_lead(db: Session, lead_id) -> Lead | None:
    stmt = select(Lead).where(Lead.lead_id == lead_id)
    return db.execute(stmt).scalar_one_or_none()


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------

#: Cột xuất ra CSV, theo đúng thứ tự này.
CSV_COLUMNS = (
    "lead_id",
    "gift_code",
    "gift_status",
    "full_name",
    "phone",
    "iphone_model",
    "iphone_year",
    "case_color",
    "company_name",
    "bni_chapter",
    "referrer_name",
    "source",
    "campaign",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "ref",
    "consent",
    "created_at",
    "updated_at",
    "redeemed_at",
    "redeemed_by",
)

#: Ký tự mở đầu khiến bảng tính coi ô là CÔNG THỨC.
#:
#: `=1+1` là công thức; `+`, `-`, `@` cũng được Excel/LibreOffice/Google Sheets
#: hiểu là bắt đầu công thức. TAB (`\t`) và CR (`\r`) nguy hiểm hơn: chúng làm
#: bộ tách ô của bảng tính hiểu sai ranh giới ô, nên phần sau khi tách lại có
#: thể trở thành công thức.
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: object) -> str:
    """Vô hiệu hoá CSV formula injection (CSV injection / formula injection).

    Vì sao phải làm: tên khách, tên công ty, `utm_content`… đều do NGƯỜI NGOÀI
    nhập vào. Nếu một ô bắt đầu bằng `=`, bảng tính sẽ THI HÀNH nó khi nhân viên
    mở file export — đó là thực thi mã phía người mở file, không phải lỗi hiển
    thị. Cách chặn đúng theo khuyến nghị OWASP: đặt một dấu nháy đơn `'` lên
    trước, biến công thức thành **chuỗi văn bản**.

    Đối chứng âm của hàm này nằm ở `tests/test_admin_leads_api.py` — bỏ hàm này
    đi thì test phải FAIL (xem docs/MASTER_STATUS.md §20).
    """
    text = "" if value is None else str(value)
    if text.startswith(CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


def lead_to_csv_row(lead: Lead) -> dict[str, str]:
    return {
        "lead_id": sanitize_csv_cell(lead.lead_id),
        "gift_code": sanitize_csv_cell(lead.gift_code),
        "gift_status": sanitize_csv_cell(lead.gift_status),
        "full_name": sanitize_csv_cell(lead.full_name),
        "phone": sanitize_csv_cell(lead.phone),
        "iphone_model": sanitize_csv_cell(lead.iphone_model),
        "iphone_year": sanitize_csv_cell(lead.iphone_year),
        "case_color": sanitize_csv_cell(lead.case_color),
        "company_name": sanitize_csv_cell(lead.company_name),
        "bni_chapter": sanitize_csv_cell(lead.bni_chapter),
        "referrer_name": sanitize_csv_cell(lead.referrer_name),
        "source": sanitize_csv_cell(lead.source),
        "campaign": sanitize_csv_cell(lead.campaign),
        "utm_source": sanitize_csv_cell(lead.utm_source),
        "utm_medium": sanitize_csv_cell(lead.utm_medium),
        "utm_campaign": sanitize_csv_cell(lead.utm_campaign),
        "utm_content": sanitize_csv_cell(lead.utm_content),
        "ref": sanitize_csv_cell(lead.ref),
        "consent": sanitize_csv_cell(lead.consent),
        "created_at": sanitize_csv_cell(lead.created_at.isoformat() if lead.created_at else ""),
        "updated_at": sanitize_csv_cell(lead.updated_at.isoformat() if lead.updated_at else ""),
        "redeemed_at": sanitize_csv_cell(lead.redeemed_at.isoformat() if lead.redeemed_at else ""),
        "redeemed_by": sanitize_csv_cell(lead.redeemed_by),
    }


@dataclass(slots=True)
class CsvExport:
    text: str
    row_count: int
    truncated: bool


def export_leads_csv(
    db: Session, filters: LeadFilters, *, max_rows: int = CSV_MAX_ROWS
) -> CsvExport:
    """Export CSV theo CÙNG bộ lọc với danh sách, có trần số dòng.

    Trần được ép bằng `LIMIT max_rows + 1`: lấy dư một dòng để **biết là đã bị
    cắt** thay vì im lặng cắt. Im lặng cắt là dạng hỏng nguy hiểm — người dùng
    nhận file thiếu dữ liệu mà không có dấu hiệu nào.
    """
    stmt = (
        build_lead_query(filters)
        .order_by(Lead.created_at.desc(), Lead.id.desc())
        .limit(max_rows + 1)
    )
    rows = list(db.execute(stmt).scalars().all())
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(CSV_COLUMNS),
        lineterminator="\r\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()
    for lead in rows:
        writer.writerow(lead_to_csv_row(lead))

    if truncated:
        logger.warning("Export CSV bị cắt ở %d dòng (còn dữ liệu khớp bộ lọc chưa xuất).", max_rows)

    return CsvExport(text=buffer.getvalue(), row_count=len(rows), truncated=truncated)
