"""API danh mục iPhone.

Landing đọc danh mục từ đây. Model mới được thêm vào database (hoặc qua
admin ở G05) mà KHÔNG phải sửa HTML.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import IphoneModel
from ..schemas import CatalogModelOut

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
