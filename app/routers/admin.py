"""Router khu vực QUẢN TRỊ (G05 leads + G06 danh mục iPhone).

RANH GIỚI XÁC THỰC — đọc trước khi sửa file này:

Mọi route trong file này **bắt buộc** có `Depends(require_staff)`. Không có
ngoại lệ, kể cả route chỉ đọc. `require_staff` **fail CLOSED**: chưa cấu hình
`STAFF_API_KEYS` thì trả **503**, không mở toang (xem `app/security.py`).

Vì sao viết thành câu ở đây: một route quên dependency thì **không có gì báo
lỗi** — nó vẫn chạy, vẫn trả 200, chỉ khác là ai cũng đọc được. Test IDOR trong
`tests/test_admin_leads_api.py` tồn tại để bắt đúng ca đó; đối chứng âm của nó
(bỏ dependency → test FAIL) ghi ở docs/MASTER_STATUS.md §20.

LƯU Ý THỨ TỰ KHAI BÁO: `/leads.csv` phải khai TRƯỚC `/leads/{lead_id}`. Nếu
không, FastAPI khớp `leads.csv` vào `{lead_id}` và trả 422 — lỗi im lặng về mặt
nghiệp vụ vì route CSV "biến mất" mà không có cảnh báo nào.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiError, NotFound
from ..models import GIFT_STATUS_VALUES, IphoneModel
from ..schemas import (
    AdminIphoneModelOut,
    AdminLeadOut,
    AdminLeadPageOut,
    IphoneModelCreateRequest,
    IphoneModelPatchRequest,
)
from ..security import require_staff
from ..services import admin_leads as admin_leads_service
from ..services.admin_leads import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    CsvExport,
    LeadFilters,
    count_leads,
    get_lead,
    list_leads,
    resolve_model_display_name,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

#: Ký tự xuống dòng trong header `Content-Disposition` bị cấm — xem `_csv_response`.
CSV_FILENAME_TEMPLATE = "vipphone-leads-{stamp}.csv"


def _filters_from_query(
    db: Session,
    *,
    phone: str | None,
    iphone_model: str | None,
    source: str | None,
    gift_status: str | None,
    created_from: dt.date | None,
    created_to: dt.date | None,
) -> LeadFilters:
    """Chuẩn hoá tham số lọc. Dùng CHUNG cho danh sách và CSV.

    `created_from` tính từ 00:00 UTC của ngày đó; `created_to` là cận trên ĐỘC
    QUYỀN nên cộng thêm một ngày — nhờ vậy lọc `from == to == một ngày` là trọn
    ngày đó, không sót giây nào.
    """
    if created_from and created_to and created_to < created_from:
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            "Khoảng ngày không hợp lệ.",
            fields={"created_to": "created_to phải lớn hơn hoặc bằng created_from."},
        )

    status = gift_status.strip().upper() if gift_status else None
    if status and status not in GIFT_STATUS_VALUES:
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            "Trạng thái quà không hợp lệ.",
            fields={"gift_status": "Chọn một trong: " + ", ".join(GIFT_STATUS_VALUES)},
        )

    model_value = None
    if iphone_model and iphone_model.strip():
        # Nhận cả `model_code` (UI chọn) và tên hiển thị (dữ liệu đã lưu).
        model_value = resolve_model_display_name(db, iphone_model)

    return LeadFilters(
        phone=phone.strip() if phone and phone.strip() else None,
        iphone_model=model_value,
        source=source.strip() if source and source.strip() else None,
        gift_status=status,
        created_from=(
            dt.datetime.combine(created_from, dt.time.min, tzinfo=dt.UTC) if created_from else None
        ),
        created_to=(
            dt.datetime.combine(created_to + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC)
            if created_to
            else None
        ),
    )


def _csv_response(export: CsvExport) -> Response:
    """Bọc CSV thành response tải về.

    Tên file do MÃ sinh (mốc thời gian), KHÔNG lấy từ tham số người dùng — nếu
    lấy từ người dùng thì phải chống header injection (CR/LF) ở đây. Vì không
    nhận từ ngoài nên không có đường chèn.
    """
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")

    # BOM UTF-8 ở đầu file.
    #
    # VÌ SAO: Excel trên Windows không suy ra bảng mã từ `charset=utf-8` trong
    # Content-Type khi người dùng bấm tải file — nó đoán theo locale máy. Không
    # có BOM thì tên khách có dấu tiếng Việt hiện sai (mojibake), trong khi dữ
    # liệu trong database hoàn toàn đúng. Đây là lỗi người dùng cuối gặp NGAY
    # lần mở file đầu tiên, nên phải vá.
    #
    # BOM chỉ là 3 byte `EF BB BF` ở đầu; mọi công cụ đọc CSV đúng chuẩn đều bỏ
    # qua nó. Có test khẳng định byte đầu là BOM và phần còn lại vẫn giải mã đúng.
    content = b"\xef\xbb\xbf" + export.text.encode("utf-8")

    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{CSV_FILENAME_TEMPLATE.format(stamp=stamp)}"',
            "Cache-Control": "no-store",
            #: Nói thẳng ra khi bị cắt trần, để người dùng biết file không đầy đủ
            #: thay vì nhận một file thiếu dữ liệu mà không có dấu hiệu nào.
            "X-VIPPHONE-CSV-Rows": str(export.row_count),
            "X-VIPPHONE-CSV-Truncated": "true" if export.truncated else "false",
        },
    )


# --------------------------------------------------------------------------
# G05 — LEADS
# --------------------------------------------------------------------------


@router.get(
    "/leads",
    response_model=AdminLeadPageOut,
    summary="Danh sách lead cho quản trị (cần xác thực)",
)
def admin_list_leads(
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
    phone: str | None = Query(default=None, max_length=32, description="Tìm một phần SĐT"),
    iphone_model: str | None = Query(default=None, max_length=120),
    source: str | None = Query(default=None, max_length=32),
    gift_status: str | None = Query(default=None, max_length=16),
    created_from: dt.date | None = Query(default=None),
    created_to: dt.date | None = Query(default=None, description="Tính trọn ngày này (bao gồm)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
) -> AdminLeadPageOut:
    """Tra cứu lead theo bộ lọc, phân trang, MỚI NHẤT TRƯỚC.

    `page_size` có TRẦN (`PAGE_SIZE_MAX`) ép bằng `le=` của FastAPI, nên xin
    nhiều hơn trần là 422 — không phải lặng lẽ cắt xuống.
    """
    del actor  # chỉ dùng để chặn truy cập

    filters = _filters_from_query(
        db,
        phone=phone,
        iphone_model=iphone_model,
        source=source,
        gift_status=gift_status,
        created_from=created_from,
        created_to=created_to,
    )
    total = count_leads(db, filters)
    items = list_leads(db, filters, page=page, page_size=page_size)

    return AdminLeadPageOut(
        items=[AdminLeadOut.model_validate(lead) for lead in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/leads.csv",
    summary="Export CSV theo CÙNG bộ lọc với danh sách (cần xác thực)",
    response_class=Response,
)
def admin_export_leads_csv(
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
    phone: str | None = Query(default=None, max_length=32),
    iphone_model: str | None = Query(default=None, max_length=120),
    source: str | None = Query(default=None, max_length=32),
    gift_status: str | None = Query(default=None, max_length=16),
    created_from: dt.date | None = Query(default=None),
    created_to: dt.date | None = Query(default=None),
) -> Response:
    """Export CSV. CÙNG hàm dựng truy vấn với danh sách, nên hai đường không lệch nhau.

    Chống **CSV formula injection** ở `app/services/admin_leads.sanitize_csv_cell`.
    Có trần số dòng (`CSV_MAX_ROWS`) và nói rõ khi bị cắt.
    """
    del actor  # chỉ dùng để chặn truy cập

    filters = _filters_from_query(
        db,
        phone=phone,
        iphone_model=iphone_model,
        source=source,
        gift_status=gift_status,
        created_from=created_from,
        created_to=created_to,
    )
    # Đọc trần qua MODULE (không import hằng số theo giá trị) để test đo được
    # đúng nhánh chạm trần mà không phải nạp 5.001 dòng vào database.
    return _csv_response(
        admin_leads_service.export_leads_csv(db, filters, max_rows=admin_leads_service.CSV_MAX_ROWS)
    )


@router.get(
    "/leads/{lead_id}",
    response_model=AdminLeadOut,
    summary="Chi tiết một lead (cần xác thực)",
)
def admin_get_lead(
    lead_id: str,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminLeadOut:
    """Chi tiết theo `lead_id` (UUID).

    Không tìm thấy → **404**, không trả dữ liệu rỗng kèm 200: 200-kèm-rỗng khiến
    UI tưởng đã lấy được bản ghi.
    """
    del actor  # chỉ dùng để chặn truy cập

    try:
        parsed = uuid.UUID(lead_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise NotFound("LEAD_NOT_FOUND", "Không tìm thấy lead.") from exc

    lead = get_lead(db, parsed)
    if lead is None:
        raise NotFound("LEAD_NOT_FOUND", "Không tìm thấy lead.")
    return AdminLeadOut.model_validate(lead)


# --------------------------------------------------------------------------
# G06 — DANH MỤC IPHONE
# --------------------------------------------------------------------------


@router.get(
    "/iphone-models",
    response_model=list[AdminIphoneModelOut],
    summary="Toàn bộ danh mục iPhone, kể cả model đã tắt (cần xác thực)",
)
def admin_list_iphone_models(
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> list[IphoneModel]:
    """Khác route công khai: trả CẢ model `active = false`, để admin bật lại được."""
    del actor  # chỉ dùng để chặn truy cập

    stmt = select(IphoneModel).order_by(
        IphoneModel.sort_order.asc(), IphoneModel.year.desc(), IphoneModel.model_code.asc()
    )
    return list(db.execute(stmt).scalars().all())


@router.post(
    "/iphone-models",
    response_model=AdminIphoneModelOut,
    status_code=201,
    summary="Thêm model vào danh mục (cần xác thực)",
)
def admin_create_iphone_model(
    payload: IphoneModelCreateRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> IphoneModel:
    """Thêm model do ADMIN nhập. Hệ thống KHÔNG tự bịa model nào.

    `year` bắt buộc >= 2007 (iPhone đời đầu) — xem `IPHONE_MIN_YEAR`.
    `model_code` phải là slug và là DUY NHẤT; trùng → **409**, không ghi đè.
    """
    del actor  # chỉ dùng để chặn truy cập

    existing = db.execute(
        select(IphoneModel).where(IphoneModel.model_code == payload.model_code)
    ).scalar_one_or_none()
    if existing is not None:
        raise ApiError(
            409,
            "MODEL_CODE_EXISTS",
            "Mã model này đã có trong danh mục.",
            fields={"model_code": "Chọn mã khác hoặc sửa model đang có (PATCH)."},
        )

    model = IphoneModel(
        year=payload.year,
        model_code=payload.model_code,
        display_name=payload.display_name,
        active=payload.active,
        sort_order=payload.sort_order,
    )
    db.add(model)
    try:
        db.commit()
    except IntegrityError as exc:
        # Hai admin thêm cùng lúc: ràng buộc UNIQUE ở DB thắng. Không nuốt lỗi.
        db.rollback()
        raise ApiError(
            409,
            "MODEL_CODE_EXISTS",
            "Mã model này đã có trong danh mục.",
            fields={"model_code": "Chọn mã khác hoặc sửa model đang có (PATCH)."},
        ) from exc

    db.refresh(model)
    return model


@router.patch(
    "/iphone-models/{model_code}",
    response_model=AdminIphoneModelOut,
    summary="Sửa model trong danh mục (cần xác thực)",
)
def admin_patch_iphone_model(
    model_code: str,
    payload: IphoneModelPatchRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> IphoneModel:
    """Sửa `display_name`, `active`, `sort_order`. KHÔNG sửa `model_code`/`year`."""
    del actor  # chỉ dùng để chặn truy cập

    code = model_code.strip().lower()
    model = db.execute(
        select(IphoneModel).where(IphoneModel.model_code == code)
    ).scalar_one_or_none()
    if model is None:
        raise NotFound("MODEL_NOT_FOUND", "Không tìm thấy model trong danh mục.")

    if payload.display_name is not None:
        model.display_name = payload.display_name
    if payload.active is not None:
        model.active = payload.active
    if payload.sort_order is not None:
        model.sort_order = payload.sort_order

    db.commit()
    db.refresh(model)
    return model
