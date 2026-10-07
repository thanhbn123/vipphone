"""G17 — Webhook thanh toán (công khai, KÝ) + API quản trị thanh toán (`require_staff`).

Webhook:
- Chữ ký + thời gian kiểm TRƯỚC khi đọc DB. Sai ⇒ 401, KHÔNG ghi gì (một kẻ gửi
  rác không được làm phình bảng vết).
- Body đọc qua trần (`read_limited_body`). Không log body, không log chữ ký.
- Trả 200 cho APPLIED và DUPLICATE (nhà cung cấp ngừng gửi lại), 4xx cho REJECTED.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiError
from ..limits import read_limited_body
from ..models import Order, Payment
from ..payments import StagingMockProvider
from ..schemas import (
    AdminPaymentOut,
    AdminPaymentPageOut,
    PaymentActionRequest,
    PaymentEventOut,
)
from ..security import require_staff
from ..services import payments as payment_service

logger = logging.getLogger("vipphone.payments")

router = APIRouter(tags=["payments"])

WEBHOOK_MAX_BYTES = 8_192


@router.post("/api/payments/webhooks/staging-mock", include_in_schema=False)
async def staging_mock_webhook(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    provider = StagingMockProvider()
    body = await read_limited_body(request, WEBHOOK_MAX_BYTES)
    if not provider.verify_webhook(request.headers, body):
        logger.warning("Webhook staging-mock bị từ chối: chữ ký/thời gian không hợp lệ")
        raise ApiError(401, "INVALID_SIGNATURE", "Chữ ký webhook không hợp lệ.")
    result = provider.handle_webhook(db, request.headers, body)
    db.commit()
    logger.info("Webhook staging-mock: %s (%s)", result.outcome, result.reason or "-")
    return JSONResponse(
        status_code=result.http_status,
        content={"outcome": result.outcome, "reason": result.reason},
    )


# --------------------------------------------------------------------------
# Quản trị
# --------------------------------------------------------------------------
def _admin_view(
    db: Session, payment: Payment, order: Order, *, with_events: bool
) -> AdminPaymentOut:
    return AdminPaymentOut(
        payment_id=payment.payment_id,
        order_id=order.order_id,
        order_number=order.order_number,
        method=payment.method,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        provider_reference=payment.provider_reference,
        confirmed_by=payment.confirmed_by,
        confirmed_at=payment.confirmed_at,
        created_at=payment.created_at,
        allowed_actions=payment_service.allowed_actions(payment),
        events=[PaymentEventOut.model_validate(e) for e in payment_service.events_for(db, payment)]
        if with_events
        else [],
    )


@router.get("/api/admin/payments", response_model=AdminPaymentPageOut)
def list_payments(
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
    status: str | None = Query(default=None, max_length=20),
    method: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AdminPaymentPageOut:
    stmt = select(Payment, Order).join(Order, Order.id == Payment.order_id)
    if status:
        stmt = stmt.where(Payment.status == status)
    if method:
        stmt = stmt.where(Payment.method == method)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Payment.created_at.desc(), Payment.id.desc()).limit(limit).offset(offset)
    ).all()
    return AdminPaymentPageOut(
        items=[_admin_view(db, p, o, with_events=False) for p, o in rows], total=total
    )


@router.get("/api/admin/orders/{order_id}/payments", response_model=list[AdminPaymentOut])
def order_payments(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> list[AdminPaymentOut]:
    order = db.execute(select(Order).where(Order.order_id == order_id)).scalar_one_or_none()
    if order is None:
        raise ApiError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
    return [
        _admin_view(db, p, order, with_events=True) for p in payment_service.payments_for(db, order)
    ]


def _act(db: Session, payment_id: uuid.UUID, action, actor: str, note: str | None):
    payment = payment_service.get_payment_for_update(db, payment_id)
    action(db, payment, actor=actor, note=note)
    db.commit()
    order = db.execute(select(Order).where(Order.id == payment.order_id)).scalar_one()
    return _admin_view(db, payment, order, with_events=True)


@router.post("/api/admin/payments/{payment_id}/confirm", response_model=AdminPaymentOut)
def confirm_payment(
    payment_id: uuid.UUID,
    payload: PaymentActionRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminPaymentOut:
    return _act(db, payment_id, payment_service.staff_confirm, actor, payload.note)


@router.post("/api/admin/payments/{payment_id}/fail", response_model=AdminPaymentOut)
def fail_payment(
    payment_id: uuid.UUID,
    payload: PaymentActionRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminPaymentOut:
    return _act(db, payment_id, payment_service.staff_fail, actor, payload.note)


@router.post("/api/admin/payments/{payment_id}/refund", response_model=AdminPaymentOut)
def refund_payment(
    payment_id: uuid.UUID,
    payload: PaymentActionRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> AdminPaymentOut:
    return _act(db, payment_id, payment_service.staff_refund, actor, payload.note)
