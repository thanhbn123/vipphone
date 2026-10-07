"""Kho — API QUẢN TRỊ (`require_staff`). Con số tồn chỉ lộ ở đây."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import NotFound
from ..models import InventoryBalance, InventoryMovement, Order, Product, ProductVariant
from ..schemas import (
    InventoryBalanceOut,
    InventoryDetailOut,
    InventoryMovementCreateRequest,
    InventoryMovementOut,
    _clean_sku,
)
from ..security import require_staff
from ..services import inventory

router = APIRouter(prefix="/api/admin/inventory", tags=["admin-inventory"])


def _variant_or_404(db: Session, sku: str) -> tuple[ProductVariant, Product]:
    try:
        code = _clean_sku(sku)
    except ValueError as exc:
        raise NotFound("SKU_NOT_FOUND", "Không tìm thấy SKU.") from exc
    row = db.execute(
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProductVariant.sku == code)
    ).first()
    if row is None:
        raise NotFound("SKU_NOT_FOUND", "Không tìm thấy SKU.")
    return row[0], row[1]


def _balance_view(
    variant: ProductVariant, product: Product, balance: InventoryBalance | None
) -> InventoryBalanceOut:
    return InventoryBalanceOut(
        sku=variant.sku,
        product_name=product.name,
        variant_name=variant.variant_name,
        stock_tracking=variant.stock_tracking,
        quantity_on_hand=balance.quantity_on_hand if balance else 0,
        quantity_reserved=balance.quantity_reserved if balance else 0,
        quantity_available=balance.quantity_available if balance else 0,
        updated_at=balance.updated_at if balance else None,
    )


@router.get("", response_model=list[InventoryBalanceOut])
def list_inventory(
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
    tracked_only: bool = Query(default=True),
    low_stock_below: int | None = Query(default=None, ge=0, le=100_000),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[InventoryBalanceOut]:
    stmt = (
        select(ProductVariant, Product, InventoryBalance)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(InventoryBalance, InventoryBalance.sku_id == ProductVariant.id)
    )
    if tracked_only:
        stmt = stmt.where(ProductVariant.stock_tracking.is_(True))
    if low_stock_below is not None:
        stmt = stmt.where(
            (InventoryBalance.quantity_available < low_stock_below) | InventoryBalance.id.is_(None)
        )
    rows = db.execute(stmt.order_by(ProductVariant.sku.asc()).limit(limit).offset(offset)).all()
    return [_balance_view(v, p, b) for v, p, b in rows]


def _detail(db: Session, variant: ProductVariant, product: Product) -> InventoryDetailOut:
    balance = db.execute(
        select(InventoryBalance).where(InventoryBalance.sku_id == variant.id)
    ).scalar_one_or_none()
    rows = db.execute(
        select(InventoryMovement, Order.order_number)
        .outerjoin(Order, Order.id == InventoryMovement.order_id)
        .where(InventoryMovement.sku_id == variant.id)
        .order_by(InventoryMovement.id.asc())
    ).all()
    return InventoryDetailOut(
        balance=_balance_view(variant, product, balance),
        movements=[
            InventoryMovementOut(
                id=m.id,
                movement_type=m.movement_type,
                delta_on_hand=m.delta_on_hand,
                delta_reserved=m.delta_reserved,
                order_number=number,
                actor=m.actor,
                reason=m.reason,
                created_at=m.created_at,
            )
            for m, number in rows
        ],
    )


@router.get("/{sku}", response_model=InventoryDetailOut)
def get_inventory(
    sku: str, db: Session = Depends(get_db), actor: str = Depends(require_staff)
) -> InventoryDetailOut:
    variant, product = _variant_or_404(db, sku)
    return _detail(db, variant, product)


@router.post(
    "/{sku}/movements", response_model=InventoryDetailOut, status_code=status.HTTP_201_CREATED
)
def create_movement(
    sku: str,
    payload: InventoryMovementCreateRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> InventoryDetailOut:
    variant, product = _variant_or_404(db, sku)
    inventory.record_manual(
        db,
        variant,
        movement_type=payload.movement_type,
        quantity=payload.quantity,
        actor=actor,
        reason=payload.reason,
    )
    db.commit()
    return _detail(db, variant, product)
