"""G14 — API CÔNG KHAI danh mục sản phẩm. KHÔNG cần khoá nhân viên.

Hai đường, và cả hai đi qua **cùng một** hàm dựng truy vấn + **cùng một** hàm
serialize trong `app/services/catalog.py`:

- `GET /api/products` — danh sách, có lọc/phân trang
- `GET /api/products/{slug}` — chi tiết

Ranh giới: đường này **chỉ** thấy sản phẩm `active` và SKU `active`. Sản phẩm đã
tắt trả **404** (không phải 403 — 403 xác nhận slug đó có tồn tại; 404 không xác
nhận gì), và **không bao giờ** trả `cost_price` (giá nhập).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import NotFound
from ..schemas import ProductOut, ProductPageOut
from ..services import catalog as catalog_service
from ..services.catalog import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, ProductFilters

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=ProductPageOut, summary="Danh sách sản phẩm đang bán")
def list_public_products(
    db: Session = Depends(get_db),
    category: str | None = Query(
        default=None, max_length=40, description="Mã category, ví dụ CASE"
    ),
    device_model: str | None = Query(
        default=None, max_length=64, description="MÃ máy, ví dụ iphone-16-pro-max"
    ),
    q: str | None = Query(default=None, max_length=120, description="Từ khoá: tên hoặc mã SKU"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
) -> ProductPageOut:
    """`page_size` có TRẦN (`le=`) ⇒ xin hơn trần là **422**, không lặng lẽ cắt xuống."""
    filters = ProductFilters(
        category_code=category,
        device_model=device_model,
        q=q,
        active_only=True,
    )
    total = catalog_service.count_products(db, filters)
    products = catalog_service.list_products(db, filters, page=page, page_size=page_size)
    return ProductPageOut(
        items=catalog_service.serialize_public(db, products),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{slug}", response_model=ProductOut, summary="Chi tiết sản phẩm theo slug")
def get_public_product(slug: str, db: Session = Depends(get_db)) -> ProductOut:
    """Không tìm thấy (hoặc sản phẩm đã tắt) ⇒ **404**, không trả 200-kèm-rỗng.

    200-kèm-rỗng khiến UI tưởng đã lấy được hàng và vẽ ra trang trắng.
    """
    product = catalog_service.get_public_product(db, slug)
    if product is None:
        raise NotFound("PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.")
    return catalog_service.serialize_public_one(db, product)
