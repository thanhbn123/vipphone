"""Ảnh sản phẩm. Thiết kế: `docs/product-images.md`.

Luật:

1. **Chỉ nhận byte ảnh tải lên**, không nhận URL. Không hotlink — ảnh nằm trong kho
   lưu của chính VIP PHONE.
2. **Không tin khai báo của client**: `Content-Type` phải khớp MAGIC BYTES, và
   Pillow phải mở + kiểm được ảnh. Trần pixel chặn "decompression bomb".
3. **Mã hoá lại** mọi ảnh ⇒ bỏ EXIF (vị trí GPS, máy chụp...) và mọi dữ liệu thừa
   giấu trong file.
4. Tối đa MỘT ảnh chính mỗi sản phẩm; ảnh đầu tiên tự là ảnh chính; xoá ảnh chính
   thì ảnh kế tiếp (theo `sort_order`, `id`) được đẩy lên.
"""

from __future__ import annotations

import hashlib
import io
import uuid
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..errors import ApiError
from ..models import Product, ProductImage
from ..storage import get_storage

MAX_PIXELS = 25_000_000
MAX_SIDE = 6000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

#: content_type ⇒ (định dạng Pillow, đuôi file, magic-bytes kiểm)
FORMATS = {
    "image/png": ("PNG", "png"),
    "image/jpeg": ("JPEG", "jpg"),
    "image/webp": ("WEBP", "webp"),
}


def _magic_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@dataclass(frozen=True)
class CleanImage:
    data: bytes
    content_type: str
    extension: str
    width: int
    height: int


def clean_image(raw: bytes, declared_type: str) -> CleanImage:
    declared = (declared_type or "").split(";")[0].strip().lower()
    if declared not in FORMATS:
        raise ApiError(415, "UNSUPPORTED_IMAGE_TYPE", "Chỉ nhận ảnh PNG, JPEG hoặc WEBP.")
    if not raw:
        raise ApiError(422, "EMPTY_IMAGE", "Tệp ảnh rỗng.")
    if _magic_type(raw) != declared:
        raise ApiError(422, "IMAGE_TYPE_MISMATCH", "Nội dung tệp không khớp loại ảnh đã khai báo.")
    pil_format, extension = FORMATS[declared]
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != pil_format:
                raise ApiError(422, "IMAGE_TYPE_MISMATCH", "Nội dung tệp không khớp loại ảnh.")
            width, height = image.size
            if width < 1 or height < 1 or width > MAX_SIDE or height > MAX_SIDE:
                raise ApiError(422, "IMAGE_DIMENSIONS", f"Mỗi cạnh ảnh tối đa {MAX_SIDE}px.")
            image.load()
            out = io.BytesIO()
            if pil_format == "JPEG":
                image.convert("RGB").save(out, "JPEG", quality=88, optimize=True)
            elif pil_format == "PNG":
                image.save(out, "PNG", optimize=True)
            else:
                image.save(out, "WEBP", quality=85)
    except ApiError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise ApiError(422, "INVALID_IMAGE", "Tệp không phải ảnh hợp lệ.") from exc
    return CleanImage(out.getvalue(), declared, extension, width, height)


def images_for(db: Session, product_ids: list[int]) -> dict[int, list[ProductImage]]:
    if not product_ids:
        return {}
    rows = db.execute(
        select(ProductImage)
        .where(ProductImage.product_id.in_(product_ids))
        .order_by(
            ProductImage.product_id,
            ProductImage.is_primary.desc(),
            ProductImage.sort_order.asc(),
            ProductImage.id.asc(),
        )
    ).scalars()
    grouped: dict[int, list[ProductImage]] = {}
    for row in rows:
        grouped.setdefault(row.product_id, []).append(row)
    return grouped


def _clear_primary(db: Session, product: Product) -> None:
    db.execute(
        update(ProductImage)
        .where(ProductImage.product_id == product.id, ProductImage.is_primary.is_(True))
        .values(is_primary=False)
    )
    db.flush()


def add_image(
    db: Session,
    product: Product,
    clean: CleanImage,
    *,
    alt_text: str,
    is_primary: bool,
    sort_order: int,
) -> ProductImage:
    existing = images_for(db, [product.id]).get(product.id, [])
    make_primary = is_primary or not existing
    if make_primary:
        _clear_primary(db, product)
    image = ProductImage(
        image_id=uuid.uuid4(),
        product_id=product.id,
        storage_key=f"products/{uuid.uuid4().hex}.{clean.extension}",
        content_type=clean.content_type,
        byte_size=len(clean.data),
        width=clean.width,
        height=clean.height,
        sha256=hashlib.sha256(clean.data).hexdigest(),
        alt_text=alt_text,
        sort_order=sort_order,
        is_primary=make_primary,
    )
    db.add(image)
    db.flush()
    # Ghi tệp SAU khi DB nhận dòng. Lỗi ghi tệp ⇒ ném lỗi ⇒ router rollback dòng.
    get_storage().put(image.storage_key, clean.data)
    return image


def get_image(db: Session, product: Product, image_id: uuid.UUID) -> ProductImage:
    image = db.execute(
        select(ProductImage).where(
            ProductImage.image_id == image_id, ProductImage.product_id == product.id
        )
    ).scalar_one_or_none()
    if image is None:
        raise ApiError(404, "IMAGE_NOT_FOUND", "Không tìm thấy ảnh.")
    return image


def update_image(
    db: Session,
    product: Product,
    image: ProductImage,
    *,
    alt_text: str | None,
    sort_order: int | None,
    is_primary: bool | None,
) -> ProductImage:
    if alt_text is not None:
        image.alt_text = alt_text
    if sort_order is not None:
        image.sort_order = sort_order
    if is_primary:
        _clear_primary(db, product)
        image.is_primary = True
    elif is_primary is False and image.is_primary:
        raise ApiError(
            409,
            "PRIMARY_REQUIRED",
            "Muốn đổi ảnh chính thì đặt ảnh KHÁC làm ảnh chính.",
        )
    db.flush()
    return image


def delete_image(db: Session, product: Product, image: ProductImage) -> str:
    """Xoá dòng; trả `storage_key` để router xoá tệp SAU KHI commit thành công."""
    was_primary = image.is_primary
    key = image.storage_key
    db.delete(image)
    db.flush()
    if was_primary:
        remaining = images_for(db, [product.id]).get(product.id, [])
        if remaining:
            remaining[0].is_primary = True
            db.flush()
    return key


def public_url(image: ProductImage) -> str:
    return get_storage().public_url(image.storage_key)


def max_bytes() -> int:
    return settings.max_image_bytes
