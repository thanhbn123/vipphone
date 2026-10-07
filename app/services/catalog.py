"""G14 — Danh mục sản phẩm: truy vấn CÔNG KHAI + thao tác QUẢN TRỊ.

Thiết kế: `docs/catalog.md`. Ba luật của file này:

1. **Lọc `active` ở MỘT chỗ.** `ProductFilters.active_only` là công tắc duy nhất;
   danh sách và chi tiết công khai đi qua CÙNG hàm dựng truy vấn và CÙNG hàm
   serialize. Nếu lọc hai nơi thì bản vá thứ hai vô tác dụng dù mã trông đúng.
2. **Lọc theo thiết bị dùng `EXISTS`, KHÔNG `JOIN`.** Một sản phẩm có 3 SKU cùng
   tương thích với một máy thì `JOIN` trả 3 dòng trùng cho cùng một sản phẩm:
   danh sách phình, `total` phân trang sai, khách thấy cùng một món nhiều lần.
3. **`cost_price` KHÔNG BAO GIỜ đi vào lược đồ công khai.** Lộ giá nhập là lộ biên
   lợi nhuận. Hai hàm serialize tách hẳn nhau để không có nhánh nào lỡ tay.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from ..models import (
    Category,
    DeviceCompatibility,
    Product,
    ProductVariant,
)
from ..schemas import (
    AVAILABILITY_IN_STOCK,
    AVAILABILITY_OUT_OF_STOCK,
    AdminProductOut,
    AdminVariantOut,
    CategoryOut,
    CompatibilityCreateRequest,
    CompatibilityOut,
    ProductCreateRequest,
    ProductOut,
    ProductPatchRequest,
    VariantCreateRequest,
    VariantOut,
    VariantPatchRequest,
)

logger = logging.getLogger(__name__)

PAGE_SIZE_DEFAULT = 24
PAGE_SIZE_MAX = 100

#: Ký tự đại diện của `LIKE`. Người dùng gõ `%` mà không escape thì nó khớp MỌI
#: thứ — ô tìm kiếm biến thành "trả về tất cả", im lặng và không báo lỗi.
_LIKE_SPECIALS = re.compile(r"([%_\\])")


def _like_pattern(value: str) -> str:
    """Bọc `%...%` cho tìm kiếm con, ĐÃ escape ký tự đại diện của người dùng."""
    return f"%{_LIKE_SPECIALS.sub(r'\\\1', value.strip())}%"


@dataclass(frozen=True)
class ProductFilters:
    """Bộ lọc dùng CHUNG cho danh sách công khai và danh sách quản trị.

    `active_only=True` là đường công khai: chỉ sản phẩm `active` và chỉ SKU
    `active`. `False` là đường quản trị: thấy cả thứ đã tắt để bật lại.
    """

    category_code: str | None = None
    device_model: str | None = None
    q: str | None = None
    active_only: bool = True


# --------------------------------------------------------------------------
# Danh mục (category)
# --------------------------------------------------------------------------
def list_categories(db: Session, *, include_inactive: bool = False) -> list[Category]:
    stmt = select(Category)
    if not include_inactive:
        stmt = stmt.where(Category.active.is_(True))
    stmt = stmt.order_by(Category.sort_order.asc(), Category.code.asc())
    return list(db.execute(stmt).scalars().all())


def get_category_by_code(db: Session, code: str) -> Category | None:
    return db.execute(
        select(Category).where(Category.code == code.strip().upper())
    ).scalar_one_or_none()


# --------------------------------------------------------------------------
# Truy vấn sản phẩm
# --------------------------------------------------------------------------
def _compatible_exists(product_id_column, *, device_model: str):
    """`EXISTS` — KHÔNG nhân bản dòng. Xem docstring đầu file, luật 2."""
    return (
        select(ProductVariant.id)
        .join(DeviceCompatibility, DeviceCompatibility.sku_id == ProductVariant.id)
        .where(
            ProductVariant.product_id == product_id_column,
            ProductVariant.active.is_(True),
            DeviceCompatibility.device_model_code == device_model,
        )
        .exists()
    )


def product_query(filters: ProductFilters) -> Select:
    """Hàm dựng truy vấn DUY NHẤT cho cả danh sách lẫn chi tiết công khai."""
    stmt = select(Product)
    if filters.active_only:
        stmt = stmt.where(Product.active.is_(True))
    if filters.category_code:
        stmt = stmt.where(
            Product.category_id.in_(
                select(Category.id).where(Category.code == filters.category_code.strip().upper())
            )
        )
    if filters.device_model:
        stmt = stmt.where(_compatible_exists(Product.id, device_model=filters.device_model.strip()))
    if filters.q and filters.q.strip():
        pattern = _like_pattern(filters.q)
        stmt = stmt.where(
            or_(
                Product.name.ilike(pattern),
                Product.slug.ilike(pattern),
                Product.id.in_(
                    select(ProductVariant.product_id).where(ProductVariant.sku.ilike(pattern))
                ),
            )
        )
    return stmt


def count_products(db: Session, filters: ProductFilters) -> int:
    subquery = product_query(filters).with_only_columns(Product.id).subquery()
    return db.execute(select(func.count()).select_from(subquery)).scalar_one()


def list_products(
    db: Session, filters: ProductFilters, *, page: int = 1, page_size: int = PAGE_SIZE_DEFAULT
) -> list[Product]:
    stmt = (
        product_query(filters)
        .order_by(Product.name.asc(), Product.id.asc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return list(db.execute(stmt).scalars().all())


def get_public_product(db: Session, slug: str) -> Product | None:
    """Chi tiết công khai. Sản phẩm không `active` ⇒ `None` ⇒ router trả 404."""
    return db.execute(
        product_query(ProductFilters(active_only=True)).where(Product.slug == slug.strip().lower())
    ).scalar_one_or_none()


def get_product_any_state(db: Session, product_id: uuid.UUID) -> Product | None:
    """Đường QUẢN TRỊ: thấy cả sản phẩm đã tắt."""
    return db.execute(select(Product).where(Product.product_id == product_id)).scalar_one_or_none()


def get_product_by_pk(db: Session, pk: int) -> Product:
    """Lấy sản phẩm theo khoá nội bộ `products.id` (dùng khi đã có SKU trong tay)."""
    return db.execute(select(Product).where(Product.id == pk)).scalar_one()


# --------------------------------------------------------------------------
# Nạp biến thể + tương thích (nạp theo lô, tránh N+1)
# --------------------------------------------------------------------------
def load_variants(
    db: Session, product_ids: list[int], *, include_inactive: bool
) -> dict[int, list[ProductVariant]]:
    if not product_ids:
        return {}
    stmt = select(ProductVariant).where(ProductVariant.product_id.in_(product_ids))
    if not include_inactive:
        stmt = stmt.where(ProductVariant.active.is_(True))
    stmt = stmt.order_by(ProductVariant.id.asc())
    grouped: dict[int, list[ProductVariant]] = {}
    for variant in db.execute(stmt).scalars().all():
        grouped.setdefault(variant.product_id, []).append(variant)
    return grouped


def load_compatibility(db: Session, sku_ids: list[int]) -> dict[int, list[DeviceCompatibility]]:
    if not sku_ids:
        return {}
    stmt = (
        select(DeviceCompatibility)
        .where(DeviceCompatibility.sku_id.in_(sku_ids))
        .order_by(
            DeviceCompatibility.device_brand.asc(),
            DeviceCompatibility.device_model_code.asc(),
        )
    )
    grouped: dict[int, list[DeviceCompatibility]] = {}
    for row in db.execute(stmt).scalars().all():
        grouped.setdefault(row.sku_id, []).append(row)
    return grouped


def _category_codes(db: Session, category_ids: list[int]) -> dict[int, Category]:
    if not category_ids:
        return {}
    rows = db.execute(select(Category).where(Category.id.in_(category_ids))).scalars().all()
    return {row.id: row for row in rows}


def _availability(variants: list[ProductVariant]) -> str:
    """Còn hàng = có ÍT NHẤT MỘT SKU `active`. KHÔNG suy từ số lượng (chưa có)."""
    return AVAILABILITY_IN_STOCK if any(v.active for v in variants) else AVAILABILITY_OUT_OF_STOCK


def serialize_public(db: Session, products: list[Product]) -> list[ProductOut]:
    """Đường CÔNG KHAI — chỉ SKU active, KHÔNG có `cost_price`."""
    if not products:
        return []
    product_ids = [p.id for p in products]
    variants_by_product = load_variants(db, product_ids, include_inactive=False)
    categories = _category_codes(db, [p.category_id for p in products])
    all_variants = [v for group in variants_by_product.values() for v in group]
    compatibility_by_sku = load_compatibility(db, [v.id for v in all_variants])

    results: list[ProductOut] = []
    for product in products:
        variants = variants_by_product.get(product.id, [])
        category = categories.get(product.category_id)
        results.append(
            ProductOut(
                product_id=product.product_id,
                name=product.name,
                slug=product.slug,
                description=product.description,
                brand=product.brand,
                category=CategoryOut.model_validate(category) if category else None,
                availability=_availability(variants),
                variants=[
                    VariantOut(
                        sku=v.sku,
                        variant_name=v.variant_name,
                        color=v.color,
                        sale_price=v.sale_price,
                        compare_at_price=v.compare_at_price,
                        currency=v.currency,
                        compatibility=[
                            CompatibilityOut.model_validate(c)
                            for c in compatibility_by_sku.get(v.id, [])
                        ],
                    )
                    for v in variants
                ],
            )
        )
    return results


def serialize_admin(db: Session, products: list[Product]) -> list[AdminProductOut]:
    """Đường QUẢN TRỊ — thấy cả SKU đã tắt, CÓ `cost_price` và cờ nội bộ."""
    if not products:
        return []
    product_ids = [p.id for p in products]
    variants_by_product = load_variants(db, product_ids, include_inactive=True)
    categories = _category_codes(db, [p.category_id for p in products])
    all_variants = [v for group in variants_by_product.values() for v in group]
    compatibility_by_sku = load_compatibility(db, [v.id for v in all_variants])

    results: list[AdminProductOut] = []
    for product in products:
        variants = variants_by_product.get(product.id, [])
        category = categories.get(product.category_id)
        results.append(
            AdminProductOut(
                product_id=product.product_id,
                name=product.name,
                slug=product.slug,
                description=product.description,
                brand=product.brand,
                category=CategoryOut.model_validate(category) if category else None,
                availability=_availability(variants),
                active=product.active,
                created_at=product.created_at,
                updated_at=product.updated_at,
                variants=[
                    AdminVariantOut(
                        sku=v.sku,
                        variant_name=v.variant_name,
                        color=v.color,
                        sale_price=v.sale_price,
                        compare_at_price=v.compare_at_price,
                        currency=v.currency,
                        active=v.active,
                        stock_tracking=v.stock_tracking,
                        cost_price=v.cost_price,
                        compatibility=[
                            CompatibilityOut.model_validate(c)
                            for c in compatibility_by_sku.get(v.id, [])
                        ],
                    )
                    for v in variants
                ],
            )
        )
    return results


def serialize_public_one(db: Session, product: Product) -> ProductOut:
    """Chi tiết công khai đi qua CHÍNH hàm của danh sách — hai đường không thể lệch."""
    return serialize_public(db, [product])[0]


def serialize_admin_one(db: Session, product: Product) -> AdminProductOut:
    return serialize_admin(db, [product])[0]


# --------------------------------------------------------------------------
# Thao tác quản trị
# --------------------------------------------------------------------------
def slugify(name: str) -> str:
    """Sinh slug GỢI Ý từ tên — admin vẫn phải xác nhận, không tự ghi ngầm.

    Tiếng Việt có dấu được chuyển về ASCII không dấu theo bảng đọc âm tiết, đủ
    cho tên phụ kiện. Kết quả có thể rỗng (tên toàn ký tự lạ) — khi đó trả chuỗi
    rỗng để lời gọi tự quyết, KHÔNG bịa một slug từ hư không.
    """
    mapping = str.maketrans(
        "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ",
        "aaaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd",
    )
    ascii_name = name.strip().lower().translate(mapping)
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", ascii_name)).strip("-")


def create_product(db: Session, payload: ProductCreateRequest) -> Product:
    """Tạo sản phẩm. Lỗi trùng `slug` do UNIQUE ở DB quyết định — router bắt
    `IntegrityError` và trả 409, không dựa vào `SELECT` trước (cuộc đua)."""
    category = get_category_by_code(db, payload.category_code)
    if category is None:
        raise LookupError("CATEGORY_NOT_FOUND")
    product = Product(
        product_id=uuid.uuid4(),
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        brand=payload.brand,
        category_id=category.id,
        active=payload.active,
    )
    db.add(product)
    db.flush()
    return product


def patch_product(db: Session, product: Product, payload: ProductPatchRequest) -> Product:
    if payload.name is not None:
        product.name = payload.name
    if payload.description is not None:
        product.description = payload.description
    if payload.brand is not None:
        product.brand = payload.brand
    if payload.active is not None:
        product.active = payload.active
    if payload.category_code is not None:
        category = get_category_by_code(db, payload.category_code)
        if category is None:
            raise LookupError("CATEGORY_NOT_FOUND")
        product.category_id = category.id
    db.flush()
    return product


def get_variant_by_sku(db: Session, sku: str) -> ProductVariant | None:
    return db.execute(
        select(ProductVariant).where(ProductVariant.sku == sku.strip().upper())
    ).scalar_one_or_none()


def create_variant(db: Session, product: Product, payload: VariantCreateRequest) -> ProductVariant:
    variant = ProductVariant(
        sku=payload.sku,
        product_id=product.id,
        variant_name=payload.variant_name,
        color=payload.color,
        cost_price=payload.cost_price,
        sale_price=payload.sale_price,
        compare_at_price=payload.compare_at_price,
        currency=payload.currency,
        active=payload.active,
        stock_tracking=payload.stock_tracking,
    )
    db.add(variant)
    db.flush()
    return variant


def patch_variant(
    db: Session, variant: ProductVariant, payload: VariantPatchRequest
) -> ProductVariant:
    """Sửa SKU. Kiểm `compare_at_price >= sale_price` trên giá TRỊ SAU KHI SỬA.

    Vì sao phải tính giá trị sau khi sửa: `PATCH` có thể chỉ gửi `sale_price`.
    Kiểm trên payload thôi thì `compare_at_price` cũ (đang nằm trong DB) không
    được đối chiếu, và DB sẽ ném lỗi 500 khó hiểu thay vì 422 rõ ràng.
    """
    sets = payload.model_fields_set
    fields = (
        "variant_name",
        "color",
        "cost_price",
        "sale_price",
        "compare_at_price",
        "currency",
        "active",
        "stock_tracking",
    )
    for name in fields:
        if name in sets:
            setattr(variant, name, getattr(payload, name))

    if variant.compare_at_price is not None and variant.compare_at_price < variant.sale_price:
        raise ValueError("compare_at_price (giá gạch) không được nhỏ hơn sale_price")

    db.flush()
    return variant


def add_compatibility(
    db: Session, variant: ProductVariant, payload: CompatibilityCreateRequest
) -> DeviceCompatibility:
    row = DeviceCompatibility(
        sku_id=variant.id,
        device_brand=payload.device_brand.strip(),
        device_model_code=payload.device_model_code,
        compatibility_type=payload.compatibility_type,
    )
    db.add(row)
    db.flush()
    return row


def delete_compatibility(db: Session, variant: ProductVariant, compatibility_id: int) -> bool:
    row = db.execute(
        select(DeviceCompatibility).where(
            DeviceCompatibility.id == compatibility_id,
            DeviceCompatibility.sku_id == variant.id,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True
