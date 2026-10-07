"""G16 — API QUẢN TRỊ đơn hàng. Mọi route bắt buộc `require_staff`.

Bản quản trị thấy đủ địa chỉ giao hàng (cần để giao), nhưng danh sách chỉ hiện
SĐT đã che — SĐT đầy đủ chỉ nằm ở trang chi tiết, nơi nhân viên thật sự cần nó.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import NotFound
from ..models import Customer, Order, OrderStatusEvent
from ..schemas import (
    AdminOrderDetailOut,
    AdminOrderPageOut,
    AdminOrderSummaryOut,
    AdminShippingOut,
    OrderItemOut,
    OrderStatusChangeRequest,
    OrderStatusEventOut,
)
from ..security import require_staff
from ..services import commerce
from ..services.gifts import mask_phone

router = APIRouter(prefix="/api/admin/orders", tags=["admin-orders"])


def _summary(order: Order, customer: Customer, item_count: int) -> AdminOrderSummaryOut:
    return AdminOrderSummaryOut(
        order_id=order.order_id,
        order_number=order.order_number,
        status=order.status,
        payment_status=order.payment_status,
        grand_total=order.grand_total,
        currency=order.currency,
        item_count=item_count,
        customer_id=customer.customer_id,
        customer_name=customer.full_name,
        phone_masked=mask_phone(customer.phone_normalized),
        created_at=order.created_at,
    )


@router.get("", response_model=AdminOrderPageOut)
def list_orders(
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
    status: str | None = Query(default=None, max_length=20),
    payment_status: str | None = Query(default=None, max_length=20),
    q: str | None = Query(default=None, max_length=40, description="Mã đơn hoặc SĐT"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AdminOrderPageOut:
    stmt = select(Order, Customer).join(Customer, Customer.id == Order.customer_id)
    if status:
        stmt = stmt.where(Order.status == status)
    if payment_status:
        stmt = stmt.where(Order.payment_status == payment_status)
    if q and q.strip():
        term = q.strip()
        digits = "".join(ch for ch in term if ch.isdigit())
        conditions = [Order.order_number == term.upper()]
        if len(digits) >= 9:
            conditions.append(Customer.phone_normalized.like(f"%{digits[-9:]}"))
        stmt = stmt.where(or_(*conditions))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit).offset(offset)
    ).all()
    counts = commerce.count_items(db, [order.id for order, _ in rows])
    return AdminOrderPageOut(
        items=[_summary(order, customer, counts.get(order.id, 0)) for order, customer in rows],
        total=total,
    )


def _order_or_404(db: Session, order_id: uuid.UUID) -> Order:
    order = db.execute(select(Order).where(Order.order_id == order_id)).scalar_one_or_none()
    if order is None:
        raise NotFound("ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
    return order


def _detail(db: Session, order: Order) -> AdminOrderDetailOut:
    customer = commerce.customer_for(db, order)
    items = commerce.order_items(db, order)
    events = (
        db.execute(
            select(OrderStatusEvent)
            .where(OrderStatusEvent.order_id == order.id)
            .order_by(OrderStatusEvent.id.asc())
        )
        .scalars()
        .all()
    )
    summary = _summary(order, customer, sum(item.quantity for item in items))
    return AdminOrderDetailOut(
        **summary.model_dump(),
        subtotal=order.subtotal,
        shipping_fee=order.shipping_fee,
        discount_total=order.discount_total,
        customer_note=order.customer_note,
        items_detail=[OrderItemOut.model_validate(item) for item in items],
        shipping=AdminShippingOut.model_validate(commerce.shipping_for(db, order)),
        events=[OrderStatusEventOut.model_validate(event) for event in events],
        allowed_transitions=sorted(commerce.ORDER_TRANSITIONS[order.status]),
    )


@router.get("/{order_id}", response_model=AdminOrderDetailOut)
def get_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminOrderDetailOut:
    return _detail(db, _order_or_404(db, order_id))


@router.post("/{order_id}/status", response_model=AdminOrderDetailOut)
def change_status(
    order_id: uuid.UUID,
    payload: OrderStatusChangeRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminOrderDetailOut:
    order = db.execute(
        select(Order).where(Order.order_id == order_id).with_for_update()
    ).scalar_one_or_none()
    if order is None:
        raise NotFound("ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
    commerce.change_order_status(
        db, order, payload.to_status.strip().upper(), actor=actor, reason=payload.reason
    )
    db.commit()
    return _detail(db, order)
