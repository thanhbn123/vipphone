"""G14 — API QUẢN TRỊ danh mục sản phẩm.

RANH GIỚI XÁC THỰC — đọc trước khi sửa file này:

Mọi route trong file này **bắt buộc** có `Depends(require_staff)`. KHÔNG có
ngoại lệ, kể cả route chỉ đọc (`GET`). `require_staff` **fail CLOSED**: chưa cấu
hình `STAFF_API_KEYS` thì trả **503**, không mở toang (xem `app/security.py`).

Vì sao viết thành câu ở đây: một route quên dependency thì **không có gì báo lỗi**
— nó vẫn chạy, vẫn trả 200, chỉ khác là ai cũng đọc được (kèm cả `cost_price`,
tức là giá nhập). Có test auth boundary cho **từng** route trong file này.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiError, NotFound
from ..schemas import (
    AdminProductOut,
    AdminProductPageOut,
    CompatibilityCreateRequest,
    PriceHistoryOut,
    ProductCreateRequest,
    ProductPatchRequest,
    VariantCreateRequest,
    VariantPatchRequest,
)
from ..security import require_staff
from ..services import catalog as catalog_service
from ..services.catalog import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, ProductFilters

router = APIRouter(tags=["admin-products"])

DUPLICATE_SLUG_MESSAGE = "Slug này đã có sản phẩm khác dùng."
DUPLICATE_SKU_MESSAGE = "Mã SKU này đã tồn tại."


def _duplicate(field: str, message: str, hint: str) -> ApiError:
    return ApiError(409, "DUPLICATE_VALUE", message, fields={field: hint})


def _product_or_404(db: Session, product_id: uuid.UUID):
    product = catalog_service.get_product_any_state(db, product_id)
    if product is None:
        raise NotFound("PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.")
    return product


def _variant_or_404(db: Session, sku: str):
    variant = catalog_service.get_variant_by_sku(db, sku)
    if variant is None:
        raise NotFound("VARIANT_NOT_FOUND", "Không tìm thấy SKU.")
    return variant


# --------------------------------------------------------------------------
# Sản phẩm
# --------------------------------------------------------------------------
@router.get(
    "/api/admin/products",
    response_model=AdminProductPageOut,
    summary="Danh sách sản phẩm cho quản trị, KỂ CẢ đã tắt (cần xác thực)",
)
def admin_list_products(
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
    category: str | None = Query(default=None, max_length=40),
    q: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
) -> AdminProductPageOut:
    """Khác đường công khai: **thấy cả sản phẩm `active = false`** và SKU đã tắt,
    để admin bật lại được. Có `cost_price` — đây là khu vực nội bộ."""
    del actor  # chỉ dùng để chặn truy cập

    filters = ProductFilters(category_code=category, q=q, active_only=False)
    total = catalog_service.count_products(db, filters)
    products = catalog_service.list_products(db, filters, page=page, page_size=page_size)
    return AdminProductPageOut(
        items=catalog_service.serialize_admin(db, products),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/api/admin/products",
    response_model=AdminProductOut,
    status_code=201,
    summary="Tạo sản phẩm (cần xác thực)",
)
def admin_create_product(
    payload: ProductCreateRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminProductOut:
    """Sản phẩm do ADMIN nhập. Hệ thống **KHÔNG** bịa sản phẩm nào.

    `slug` trùng ⇒ **409**, không ghi đè. Áp cả hai lớp: `SELECT` trước cho thông
    báo rõ, và `IntegrityError` cho cuộc đua — hai admin tạo cùng lúc thì ràng
    buộc UNIQUE ở DB thắng.
    """
    del actor  # chỉ dùng để chặn truy cập

    try:
        product = catalog_service.create_product(db, payload)
    except LookupError as exc:
        db.rollback()
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            "Dữ liệu gửi lên không hợp lệ.",
            fields={"category_code": "Không có category với mã này."},
        ) from exc
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate("slug", DUPLICATE_SLUG_MESSAGE, "Chọn slug khác.") from exc

    db.commit()
    db.refresh(product)
    return catalog_service.serialize_admin_one(db, product)


@router.get(
    "/api/admin/products/{product_id}",
    response_model=AdminProductOut,
    summary="Chi tiết một sản phẩm, kể cả đã tắt (cần xác thực)",
)
def admin_get_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminProductOut:
    del actor  # chỉ dùng để chặn truy cập
    return catalog_service.serialize_admin_one(db, _product_or_404(db, product_id))


@router.patch(
    "/api/admin/products/{product_id}",
    response_model=AdminProductOut,
    summary="Sửa sản phẩm, gồm bật/tắt (cần xác thực)",
)
def admin_patch_product(
    product_id: uuid.UUID,
    payload: ProductPatchRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminProductOut:
    """Sửa `name`, `description`, `brand`, `category_code`, `active`.

    Bật/tắt cũng đi qua đây (`active: true|false`) — một đường duy nhất, không có
    route `activate`/`deactivate` riêng để hai đường không lệch luật.
    """
    del actor  # chỉ dùng để chặn truy cập

    product = _product_or_404(db, product_id)
    try:
        catalog_service.patch_product(db, product, payload)
    except LookupError as exc:
        db.rollback()
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            "Dữ liệu gửi lên không hợp lệ.",
            fields={"category_code": "Không có category với mã này."},
        ) from exc

    db.commit()
    db.refresh(product)
    return catalog_service.serialize_admin_one(db, product)


# --------------------------------------------------------------------------
# SKU (biến thể)
# --------------------------------------------------------------------------
@router.post(
    "/api/admin/products/{product_id}/variants",
    response_model=AdminProductOut,
    status_code=201,
    summary="Tạo SKU cho sản phẩm (cần xác thực)",
)
def admin_create_variant(
    product_id: uuid.UUID,
    payload: VariantCreateRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminProductOut:
    """`sku` trùng ⇒ **409**. Giá là `Decimal`; `compare_at_price` < `sale_price`
    bị chặn từ tầng lược đồ (422) trước khi chạm DB."""
    product = _product_or_404(db, product_id)
    # Trigger lịch sử giá ghi giá khởi điểm với ĐÚNG người tạo.
    catalog_service.stamp_change_context(db, actor=actor, reason="Tạo SKU")
    if catalog_service.get_variant_by_sku(db, payload.sku) is not None:
        raise _duplicate("sku", DUPLICATE_SKU_MESSAGE, "Chọn mã SKU khác.")

    try:
        catalog_service.create_variant(db, product, payload)
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate("sku", DUPLICATE_SKU_MESSAGE, "Chọn mã SKU khác.") from exc

    db.commit()
    db.refresh(product)
    return catalog_service.serialize_admin_one(db, product)


@router.patch(
    "/api/admin/variants/{sku}",
    response_model=AdminProductOut,
    summary="Sửa SKU / đặt giá (cần xác thực)",
)
def admin_patch_variant(
    sku: str,
    payload: VariantPatchRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminProductOut:
    """Sửa `variant_name`, `color`, giá, `currency`, `active`, `stock_tracking`.

    KHÔNG cho sửa `sku` (mã hàng là khoá tra cứu) và không đổi `product_id`.
    """
    variant = _variant_or_404(db, sku)
    # Lịch sử giá do TRIGGER DB ghi trong CÙNG giao dịch — xem migration 0012.
    catalog_service.stamp_change_context(db, actor=actor, reason=payload.price_change_reason)
    try:
        catalog_service.patch_variant(db, variant, payload)
    except ValueError as exc:
        db.rollback()
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            "Dữ liệu gửi lên không hợp lệ.",
            fields={"compare_at_price": str(exc)},
        ) from exc
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "DUPLICATE_VALUE", "Xung đột dữ liệu.", fields={}) from exc

    product = catalog_service.get_product_by_pk(db, variant.product_id)
    db.commit()
    db.refresh(product)
    return catalog_service.serialize_admin_one(db, product)


@router.get(
    "/api/admin/variants/{sku}/price-history",
    response_model=list[PriceHistoryOut],
    summary="Lịch sử giá bán của SKU (cần xác thực)",
)
def admin_price_history(
    sku: str,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> list[PriceHistoryOut]:
    variant = _variant_or_404(db, sku)
    return [
        PriceHistoryOut.model_validate(row) for row in catalog_service.price_history(db, variant)
    ]


# --------------------------------------------------------------------------
# Tương thích thiết bị
# --------------------------------------------------------------------------
@router.post(
    "/api/admin/variants/{sku}/compatibility",
    response_model=AdminProductOut,
    status_code=201,
    summary="Khai báo máy tương thích cho SKU (cần xác thực)",
)
def admin_add_compatibility(
    sku: str,
    payload: CompatibilityCreateRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminProductOut:
    """`device_model_code` là **MÃ** (`iphone-16-pro-max`), không phải tên hiển thị.

    Khai trùng cùng SKU + cùng máy ⇒ **409** (UNIQUE ở DB).
    """
    del actor  # chỉ dùng để chặn truy cập

    variant = _variant_or_404(db, sku)
    try:
        catalog_service.add_compatibility(db, variant, payload)
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate(
            "device_model_code",
            "SKU này đã khai báo tương thích cho máy đó.",
            "Sửa bản ghi đang có thay vì thêm mới.",
        ) from exc

    product = catalog_service.get_product_by_pk(db, variant.product_id)
    db.commit()
    db.refresh(product)
    return catalog_service.serialize_admin_one(db, product)


@router.delete(
    "/api/admin/variants/{sku}/compatibility/{compatibility_id}",
    response_model=AdminProductOut,
    summary="Gỡ khai báo tương thích (cần xác thực)",
)
def admin_delete_compatibility(
    sku: str,
    compatibility_id: int,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminProductOut:
    del actor  # chỉ dùng để chặn truy cập

    variant = _variant_or_404(db, sku)
    if not catalog_service.delete_compatibility(db, variant, compatibility_id):
        raise NotFound("COMPATIBILITY_NOT_FOUND", "Không tìm thấy khai báo tương thích.")

    product = catalog_service.get_product_by_pk(db, variant.product_id)
    db.commit()
    db.refresh(product)
    return catalog_service.serialize_admin_one(db, product)
