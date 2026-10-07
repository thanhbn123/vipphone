"""API danh mục iPhone.

Landing đọc danh mục từ đây. Model mới được thêm vào database (hoặc qua
admin ở G05) mà KHÔNG phải sửa HTML.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Category, IphoneModel
from ..schemas import CatalogModelOut, CategoryOut
from ..services import catalog as catalog_service

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get(
    "/iphone-models",
    response_model=list[CatalogModelOut],
    summary="Danh sách iPhone đang hoạt động",
)
def list_iphone_models(db: Session = Depends(get_db)) -> list[IphoneModel]:
    stmt = (
        select(IphoneModel)
        .where(IphoneModel.active.is_(True))
        .order_by(
            IphoneModel.sort_order.asc(), IphoneModel.year.desc(), IphoneModel.display_name.asc()
        )
    )
    return list(db.execute(stmt).scalars().all())


@router.get(
    "/categories",
    response_model=list[CategoryOut],
    summary="Danh mục nhóm hàng đang hoạt động (G14)",
)
def list_product_categories(db: Session = Depends(get_db)) -> list[Category]:
    """Nhóm hàng của danh mục sản phẩm.

    Vì sao đặt ở ĐÂY chứ không ở `/api/products/categories`: `/api/products/{slug}`
    sẽ nuốt mất đường dẫn tĩnh đó và trả 404 cho một slug tên "categories" — lỗi
    im lặng về mặt nghiệp vụ, đúng loại bẫy đã ghi ở `app/routers/admin.py`
    (`/leads.csv` phải khai TRƯỚC `/leads/{lead_id}`).

    Chỉ trả category `active` — UI lọc không cần thấy nhóm đã tắt.
    """
    return catalog_service.list_categories(db)
