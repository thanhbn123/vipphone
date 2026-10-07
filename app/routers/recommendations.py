"""G15 — API CÔNG KHAI gợi ý phụ kiện: `GET /api/recommendations`.

Ranh giới: đầu vào DUY NHẤT là MÃ MÁY. Không có tham số nào về khách, nên đường
này không thể lộ PII khách — kể cả khi bị gọi bởi người lạ. Gợi ý theo khách cụ
thể (nếu cần sau này) phải đi qua `require_staff`, không đi qua đây.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiError
from ..schemas import RecommendationsOut
from ..services import recommendations as reco_service

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("", response_model=RecommendationsOut, summary="Gợi ý phụ kiện theo dòng máy")
def get_recommendations(
    db: Session = Depends(get_db),
    device_model: str = Query(
        min_length=1, max_length=64, description="MÃ máy, ví dụ iphone-16-pro-max"
    ),
    limit: int = Query(default=reco_service.LIMIT_DEFAULT, ge=1, le=reco_service.LIMIT_MAX),
) -> RecommendationsOut:
    """Máy không có trong danh mục đang hoạt động ⇒ **422**, không trả 200-rỗng.

    200-rỗng cho một mã máy gõ sai sẽ trông y như "chưa có phụ kiện" — và che mất
    lỗi ở phía gọi.
    """
    code = device_model.strip().lower()
    if not reco_service.is_known_device(db, code):
        raise ApiError(
            422,
            "MODEL_NOT_IN_CATALOG",
            "Dòng máy này không có trong danh mục đang hoạt động.",
            fields={"device_model": "Mã máy không hợp lệ."},
        )
    return reco_service.recommend(db, device_model=code, limit=limit)
