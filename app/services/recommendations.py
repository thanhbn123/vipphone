"""G15 — Engine gợi ý phụ kiện V1: theo LUẬT, XÁC ĐỊNH, không AI/ML.

Thiết kế: `docs/recommendation-engine.md`. Bốn luật của file này:

1. **Không viết đường lọc thứ hai.** Tương thích + `active` đi qua ĐÚNG
   `catalog.product_query(ProductFilters(device_model=..., active_only=True))`
   của G14. Hai đường lọc thì sớm muộn sẽ lệch, và đường lệch là đường lộ hàng
   đã tắt.
2. **Thứ tự nhóm hàng là DỮ LIỆU** (`recommendation_category_priority`), không
   hard-code ở đây. Nhóm KHÔNG có trong bảng của ngữ cảnh ⇒ KHÔNG được gợi ý
   (nhờ vậy `CASE` tự bị loại ở `POST_GIFT` mà không cần `if` nào).
3. **Sắp xếp xác định toàn phần:** `priority ASC, products.name ASC,
   products.id ASC`. `products.id` là khoá phá hoà cuối cùng và là duy nhất ⇒
   cùng đầu vào luôn ra cùng thứ tự.
4. **Chỉ trả SKU tương thích ĐÚNG máy.** Sản phẩm có SKU cho iPhone 15 lẫn 16
   thì khách iPhone 16 chỉ thấy SKU iPhone 16 — thấy SKU kia là mời mua nhầm.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Category, IphoneModel, Product, RecommendationCategoryPriority
from ..schemas import RecommendationItemOut, RecommendationsOut
from . import catalog as catalog_service
from .catalog import ProductFilters

POST_GIFT_CONTEXT = "POST_GIFT"
LIMIT_DEFAULT = 8
LIMIT_MAX = 24


def is_known_device(db: Session, model_code: str) -> bool:
    """Máy phải có trong danh mục ĐANG HOẠT ĐỘNG — không gợi ý cho máy bịa."""
    return (
        db.execute(
            select(IphoneModel.id).where(
                IphoneModel.model_code == model_code, IphoneModel.active.is_(True)
            )
        ).first()
        is not None
    )


def recommend(
    db: Session,
    *,
    device_model: str,
    context: str = POST_GIFT_CONTEXT,
    limit: int = LIMIT_DEFAULT,
    exclude_product_ids: Iterable[int] = (),
) -> RecommendationsOut:
    """Danh sách gợi ý cho MỘT máy.

    `exclude_product_ids` là điểm mở rộng để loại hàng khách đã mua (G16). Nó
    nhận khoá NỘI BỘ `products.id`, không nhận gì từ trình duyệt.
    """
    device_model = device_model.strip().lower()

    base = catalog_service.product_query(
        ProductFilters(device_model=device_model, active_only=True)
    )
    stmt = (
        base.join(Category, Category.id == Product.category_id)
        .join(
            RecommendationCategoryPriority,
            RecommendationCategoryPriority.category_code == Category.code,
        )
        .where(
            Category.active.is_(True),
            RecommendationCategoryPriority.context == context,
            RecommendationCategoryPriority.active.is_(True),
        )
        .add_columns(Category.code, RecommendationCategoryPriority.priority)
        .order_by(
            RecommendationCategoryPriority.priority.asc(),
            Product.name.asc(),
            Product.id.asc(),
        )
        .limit(limit)
    )
    excluded = list(exclude_product_ids)
    if excluded:
        stmt = stmt.where(Product.id.not_in(excluded))

    rows = db.execute(stmt).all()
    products = [row[0] for row in rows]
    serialized = catalog_service.serialize_public(db, products)

    items: list[RecommendationItemOut] = []
    for rank, (row, product_out) in enumerate(zip(rows, serialized, strict=True), start=1):
        # Luật 4: chỉ giữ SKU tương thích ĐÚNG máy này.
        compatible_variants = [
            variant
            for variant in product_out.variants
            if any(c.device_model_code == device_model for c in variant.compatibility)
        ]
        items.append(
            RecommendationItemOut(
                rank=rank,
                category_code=row[1],
                product=product_out.model_copy(update={"variants": compatible_variants}),
            )
        )

    return RecommendationsOut(context=context, device_model_code=device_model, items=items)
