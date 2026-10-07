"""Kho tối giản. Thiết kế: `docs/inventory.md`.

Luật:

1. **Một đường ghi duy nhất**: `_apply()` khoá dòng số dư (`FOR UPDATE`), đổi số
   dư VÀ ghi một dòng sổ cái trong CÙNG giao dịch. Không có chỗ nào khác sửa số dư.
2. **Không bán vượt**: giữ hàng khi checkout chỉ thành công nếu `available >= qty`
   sau khi đã khoá dòng. Khoá theo thứ tự `sku_id` tăng dần ⇒ hai đơn nhiều SKU
   không khoá chéo nhau (deadlock).
3. Chỉ SKU bật `stock_tracking` bị kiểm/giữ. SKU không theo dõi bán như G14.
4. Bất biến cuối cùng nằm ở DB (CHECK) — tầng ứng dụng sai thì DB từ chối.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import (
    InventoryBalance,
    InventoryMovement,
    MovementType,
    Order,
    OrderItem,
    OrderStatus,
    ProductVariant,
)

#: Loại biến động nhân viên được ghi tay. RESERVE/RELEASE/SALE chỉ do đơn hàng sinh ra.
MANUAL_TYPES = {
    MovementType.OPENING.value,
    MovementType.RECEIPT.value,
    MovementType.ADJUSTMENT.value,
    MovementType.RETURN.value,
}


def _balance_for_update(db: Session, sku_id: int, *, create: bool) -> InventoryBalance | None:
    balance = db.execute(
        select(InventoryBalance).where(InventoryBalance.sku_id == sku_id).with_for_update()
    ).scalar_one_or_none()
    if balance is None and create:
        # INSERT … ON CONFLICT DO NOTHING rồi khoá lại: hai request cùng tạo số dư
        # đầu tiên không được sinh hai dòng.
        from sqlalchemy.dialects.postgresql import insert

        db.execute(
            insert(InventoryBalance)
            .values(sku_id=sku_id, quantity_on_hand=0, quantity_reserved=0)
            .on_conflict_do_nothing(index_elements=["sku_id"])
        )
        balance = db.execute(
            select(InventoryBalance).where(InventoryBalance.sku_id == sku_id).with_for_update()
        ).scalar_one()
    return balance


def _apply(
    db: Session,
    balance: InventoryBalance,
    *,
    movement_type: str,
    delta_on_hand: int,
    delta_reserved: int,
    actor: str,
    reason: str | None = None,
    order_id: int | None = None,
) -> InventoryMovement:
    new_on_hand = balance.quantity_on_hand + delta_on_hand
    new_reserved = balance.quantity_reserved + delta_reserved
    if new_on_hand < 0 or new_reserved < 0 or new_reserved > new_on_hand:
        raise ApiError(
            409,
            "INVENTORY_INVARIANT",
            "Biến động này làm tồn kho âm hoặc giữ vượt số đang có.",
        )
    balance.quantity_on_hand = new_on_hand
    balance.quantity_reserved = new_reserved
    movement = InventoryMovement(
        sku_id=balance.sku_id,
        movement_type=movement_type,
        delta_on_hand=delta_on_hand,
        delta_reserved=delta_reserved,
        order_id=order_id,
        actor=actor,
        reason=reason,
    )
    db.add(movement)
    db.flush()
    db.refresh(balance)
    return movement


# --------------------------------------------------------------------------
# Thao tác tay của nhân viên
# --------------------------------------------------------------------------
def record_manual(
    db: Session,
    variant: ProductVariant,
    *,
    movement_type: str,
    quantity: int,
    actor: str,
    reason: str | None,
) -> InventoryMovement:
    if movement_type not in MANUAL_TYPES:
        raise ApiError(
            422,
            "MOVEMENT_TYPE_NOT_ALLOWED",
            "Chỉ ghi tay được OPENING, RECEIPT, ADJUSTMENT, RETURN.",
        )
    if movement_type != MovementType.ADJUSTMENT and quantity <= 0:
        raise ApiError(422, "QUANTITY_MUST_BE_POSITIVE", "Số lượng phải lớn hơn 0.")
    if movement_type == MovementType.ADJUSTMENT and quantity == 0:
        raise ApiError(422, "QUANTITY_MUST_NOT_BE_ZERO", "Điều chỉnh phải khác 0.")
    if movement_type in (MovementType.ADJUSTMENT, MovementType.RETURN) and not reason:
        raise ApiError(
            422,
            "REASON_REQUIRED",
            "Điều chỉnh / trả hàng bắt buộc ghi lý do.",
            fields={"reason": "Bắt buộc."},
        )

    balance = _balance_for_update(db, variant.id, create=True)
    if movement_type == MovementType.OPENING:
        has_history = db.execute(
            select(InventoryMovement.id).where(InventoryMovement.sku_id == variant.id).limit(1)
        ).first()
        if has_history is not None:
            raise ApiError(
                409,
                "OPENING_ALREADY_RECORDED",
                "SKU này đã có sổ kho — dùng RECEIPT hoặc ADJUSTMENT.",
            )
    return _apply(
        db,
        balance,
        movement_type=movement_type,
        delta_on_hand=quantity,
        delta_reserved=0,
        actor=actor,
        reason=reason,
    )


# --------------------------------------------------------------------------
# Móc vào đơn hàng
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class _Line:
    sku_id: int
    sku: str
    quantity: int


def _tracked_lines(db: Session, order: Order) -> list[_Line]:
    rows = db.execute(
        select(OrderItem.sku_id, OrderItem.sku, OrderItem.quantity)
        .join(ProductVariant, ProductVariant.id == OrderItem.sku_id)
        .where(OrderItem.order_id == order.id, ProductVariant.stock_tracking.is_(True))
        .order_by(OrderItem.sku_id.asc())  # luật 2: thứ tự khoá cố định
    ).all()
    return [_Line(sku_id, sku, qty) for sku_id, sku, qty in rows]


def checkout_hook(db: Session, order: Order, payload) -> None:
    """Giữ hàng cho mọi SKU có theo dõi. Thiếu ⇒ 409, CẢ ĐƠN rollback."""
    short: list[str] = []
    for line in _tracked_lines(db, order):
        balance = _balance_for_update(db, line.sku_id, create=False)
        available = balance.quantity_available if balance is not None else 0
        if balance is None or available < line.quantity:
            short.append(line.sku)
            continue
        _apply(
            db,
            balance,
            movement_type=MovementType.RESERVE.value,
            delta_on_hand=0,
            delta_reserved=line.quantity,
            actor="customer:checkout",
            order_id=order.id,
        )
    if short:
        raise ApiError(
            409,
            "OUT_OF_STOCK",
            "Một số sản phẩm không đủ hàng. Vui lòng giảm số lượng hoặc bỏ khỏi giỏ.",
            fields={"skus": ",".join(short)},
        )


def reserved_for_order(db: Session, order: Order) -> dict[int, int]:
    """Số đang giữ cho đơn theo SKU = tổng delta_reserved của đơn (sổ cái là nguồn)."""
    rows = db.execute(
        select(InventoryMovement.sku_id, func.sum(InventoryMovement.delta_reserved))
        .where(InventoryMovement.order_id == order.id)
        .group_by(InventoryMovement.sku_id)
        .order_by(InventoryMovement.sku_id.asc())
    ).all()
    return {sku_id: int(total) for sku_id, total in rows if int(total) > 0}


def on_order_status(
    db: Session, order: Order, from_status: str, to_status: str, actor: str
) -> None:
    """Huỷ ⇒ NHẢ hàng giữ. Giao đi (SHIPPED) ⇒ BÁN: trừ on_hand + trừ reserved."""
    if to_status not in (OrderStatus.CANCELLED, OrderStatus.SHIPPED):
        return
    held = reserved_for_order(db, order)
    for sku_id, quantity in held.items():
        balance = _balance_for_update(db, sku_id, create=False)
        if to_status == OrderStatus.CANCELLED:
            _apply(
                db,
                balance,
                movement_type=MovementType.RELEASE.value,
                delta_on_hand=0,
                delta_reserved=-quantity,
                actor=actor,
                reason="Đơn bị huỷ",
                order_id=order.id,
            )
        else:
            _apply(
                db,
                balance,
                movement_type=MovementType.SALE.value,
                delta_on_hand=-quantity,
                delta_reserved=-quantity,
                actor=actor,
                reason="Đơn đã giao đi",
                order_id=order.id,
            )


# --------------------------------------------------------------------------
# Đọc
# --------------------------------------------------------------------------
def available_by_sku(db: Session, sku_ids: list[int]) -> dict[int, int]:
    if not sku_ids:
        return {}
    rows = db.execute(
        select(InventoryBalance.sku_id, InventoryBalance.quantity_available).where(
            InventoryBalance.sku_id.in_(sku_ids)
        )
    ).all()
    return {int(sku_id): int(available) for sku_id, available in rows}
