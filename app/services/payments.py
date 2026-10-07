"""G17 — Dịch vụ thanh toán: máy trạng thái + đồng bộ đơn. Thiết kế: `docs/payments.md`.

Luật:

1. **Đường duy nhất** đổi `payments.status` là `transition()`. Nó cũng là đường
   DUY NHẤT (qua `commerce.set_payment_status`) đổi `orders.payment_status`.
   Mỗi lần đổi ghi đúng một `payment_events` (APPLIED).
2. **COD không tự thành PAID.** Chỉ nhân viên xác nhận, và chỉ khi đơn đã giao đi.
3. **Chuyển khoản thủ công** PENDING cho tới khi nhân viên xác nhận.
4. **STAGING_MOCK** chỉ đổi qua webhook đã ký — nhân viên không "bấm cho thành PAID".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..errors import ApiError, NotFound
from ..models import (
    Order,
    OrderStatus,
    Payment,
    PaymentEvent,
    PaymentMethod,
    PaymentState,
    PaymentStatus,
)
from ..payments import get_provider, method_available
from . import commerce

#: Chuyển trạng thái KHOẢN THU hợp lệ. FAILED/CANCELLED/REFUNDED là trạng thái cuối.
PAYMENT_STATE_TRANSITIONS: dict[str, frozenset[str]] = {
    PaymentState.CREATED: frozenset(
        {PaymentState.PENDING, PaymentState.FAILED, PaymentState.CANCELLED}
    ),
    PaymentState.PENDING: frozenset(
        {PaymentState.PAID, PaymentState.FAILED, PaymentState.CANCELLED}
    ),
    PaymentState.PAID: frozenset({PaymentState.REFUNDED}),
    PaymentState.FAILED: frozenset(),
    PaymentState.CANCELLED: frozenset(),
    PaymentState.REFUNDED: frozenset(),
}

#: Trạng thái khoản thu ⇒ `orders.payment_status`.
ORDER_PAYMENT_STATUS = {
    PaymentState.CREATED: PaymentStatus.UNPAID,
    PaymentState.PENDING: PaymentStatus.PENDING,
    PaymentState.PAID: PaymentStatus.PAID,
    PaymentState.FAILED: PaymentStatus.FAILED,
    PaymentState.CANCELLED: PaymentStatus.UNPAID,
    PaymentState.REFUNDED: PaymentStatus.REFUNDED,
}


def can_transition(current: str, target: str) -> bool:
    return target in PAYMENT_STATE_TRANSITIONS.get(current, frozenset())


def _order_of(db: Session, payment: Payment, *, lock: bool = False) -> Order:
    stmt = select(Order).where(Order.id == payment.order_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one()


def transition(
    db: Session,
    payment: Payment,
    target: str,
    *,
    actor: str,
    event_type: str,
    provider: str = "internal",
    provider_event_id: str | None = None,
    payload_sha256: str | None = None,
    reason: str | None = None,
) -> Payment:
    current = payment.status
    if not can_transition(current, target):
        raise ApiError(
            409,
            "INVALID_PAYMENT_TRANSITION",
            f"Không thể chuyển khoản thu từ {current} sang {target}.",
        )
    payment.status = target
    if target == PaymentState.PAID:
        payment.confirmed_by = actor
        payment.confirmed_at = datetime.now(UTC)
    db.add(
        PaymentEvent(
            payment_id=payment.id,
            provider=provider,
            provider_event_id=provider_event_id or f"internal:{uuid.uuid4().hex}",
            event_type=event_type,
            from_status=current,
            to_status=target,
            amount=payment.amount,
            currency=payment.currency,
            outcome="APPLIED",
            reason=reason,
            payload_sha256=payload_sha256,
            actor=actor,
        )
    )
    order = _order_of(db, payment, lock=True)
    commerce.set_payment_status(
        db, order, ORDER_PAYMENT_STATUS[PaymentState(target)].value, actor=actor, reason=reason
    )
    db.flush()
    return payment


# --------------------------------------------------------------------------
# Checkout + huỷ đơn (hook)
# --------------------------------------------------------------------------
def checkout_hook(db: Session, order: Order, payload) -> None:
    """Chạy TRONG giao dịch checkout: tạo khoản thu theo phương thức khách chọn."""
    method = payload.payment_method
    if not method_available(method):
        raise ApiError(
            422,
            "PAYMENT_METHOD_UNAVAILABLE",
            "Phương thức thanh toán này hiện không dùng được.",
            fields={"payment_method": "Chọn phương thức khác."},
        )
    provider = get_provider(method)
    payment = provider.create_payment(db, order)
    db.add(payment)
    db.flush()
    db.add(
        PaymentEvent(
            payment_id=payment.id,
            provider="internal",
            provider_event_id=f"internal:{uuid.uuid4().hex}",
            event_type="payment.created",
            from_status=None,
            to_status=payment.status,
            amount=payment.amount,
            currency=payment.currency,
            outcome="APPLIED",
            actor="customer:checkout",
        )
    )
    commerce.set_payment_status(
        db,
        order,
        ORDER_PAYMENT_STATUS[PaymentState(payment.status)].value,
        actor="customer:checkout",
    )


def open_payment(db: Session, order: Order) -> Payment | None:
    return db.execute(
        select(Payment)
        .where(
            Payment.order_id == order.id,
            Payment.status.in_(
                [PaymentState.CREATED.value, PaymentState.PENDING.value, PaymentState.PAID.value]
            ),
        )
        .with_for_update()
    ).scalar_one_or_none()


def on_order_status(
    db: Session, order: Order, from_status: str, to_status: str, actor: str
) -> None:
    """Huỷ đơn ⇒ huỷ khoản thu ĐANG CHỜ. Khoản đã PAID giữ nguyên chờ hoàn tiền."""
    if to_status != OrderStatus.CANCELLED:
        return
    payment = open_payment(db, order)
    if payment is not None and payment.status in (PaymentState.CREATED, PaymentState.PENDING):
        transition(
            db,
            payment,
            PaymentState.CANCELLED.value,
            actor=actor,
            event_type="order.cancelled",
            reason="Đơn bị huỷ",
        )


# --------------------------------------------------------------------------
# Thao tác nhân viên
# --------------------------------------------------------------------------
def get_payment_for_update(db: Session, payment_id: uuid.UUID) -> Payment:
    payment = db.execute(
        select(Payment).where(Payment.payment_id == payment_id).with_for_update()
    ).scalar_one_or_none()
    if payment is None:
        raise NotFound("PAYMENT_NOT_FOUND", "Không tìm thấy khoản thanh toán.")
    return payment


def staff_confirm(db: Session, payment: Payment, *, actor: str, note: str | None) -> Payment:
    order = _order_of(db, payment, lock=True)
    if payment.method == PaymentMethod.STAGING_MOCK:
        raise ApiError(
            409,
            "CONFIRM_NOT_ALLOWED",
            "Khoản thu qua cổng chỉ được xác nhận bằng webhook đã ký, không xác nhận tay.",
        )
    if order.status == OrderStatus.CANCELLED:
        raise ApiError(409, "ORDER_CANCELLED", "Đơn đã huỷ — không xác nhận thu tiền.")
    if payment.method == PaymentMethod.COD and order.status not in (
        OrderStatus.SHIPPED,
        OrderStatus.COMPLETED,
    ):
        raise ApiError(
            409,
            "COD_NOT_DELIVERED",
            "COD chỉ xác nhận đã thu khi đơn đã giao đi (SHIPPED/COMPLETED).",
        )
    return transition(
        db,
        payment,
        PaymentState.PAID.value,
        actor=actor,
        event_type="staff.confirmed",
        reason=note,
    )


def staff_fail(db: Session, payment: Payment, *, actor: str, note: str | None) -> Payment:
    if payment.method == PaymentMethod.STAGING_MOCK:
        raise ApiError(409, "CONFIRM_NOT_ALLOWED", "Khoản thu qua cổng chỉ đổi bằng webhook.")
    return transition(
        db, payment, PaymentState.FAILED.value, actor=actor, event_type="staff.failed", reason=note
    )


def staff_refund(db: Session, payment: Payment, *, actor: str, note: str | None) -> Payment:
    order = _order_of(db, payment, lock=True)
    if order.status != OrderStatus.CANCELLED:
        raise ApiError(409, "REFUND_REQUIRES_CANCELLED_ORDER", "Chỉ hoàn tiền cho đơn đã huỷ.")
    return transition(
        db,
        payment,
        PaymentState.REFUNDED.value,
        actor=actor,
        event_type="staff.refunded",
        reason=note,
    )


def payments_for(db: Session, order: Order) -> list[Payment]:
    return list(
        db.execute(select(Payment).where(Payment.order_id == order.id).order_by(Payment.id.asc()))
        .scalars()
        .all()
    )


def events_for(db: Session, payment: Payment) -> list[PaymentEvent]:
    return list(
        db.execute(
            select(PaymentEvent)
            .where(PaymentEvent.payment_id == payment.id)
            .order_by(PaymentEvent.id.asc())
        )
        .scalars()
        .all()
    )


def instructions_for(payment: Payment, order: Order) -> str | None:
    if payment.method == PaymentMethod.BANK_TRANSFER_MANUAL:
        base = f"Ghi nội dung chuyển khoản: {order.order_number}."
        extra = settings.bank_transfer_instructions.strip()
        return f"{base} {extra}" if extra else f"{base} VIP PHONE sẽ liên hệ xác nhận."
    if payment.method == PaymentMethod.COD:
        return "Thanh toán tiền mặt khi nhận hàng."
    return None


def public_payment(db: Session, order: Order):
    """Khoản thu MỚI NHẤT của đơn, bản cho chủ đơn."""
    from ..schemas import PaymentPublicOut

    rows = payments_for(db, order)
    if not rows:
        return None
    payment = rows[-1]
    return PaymentPublicOut(
        method=payment.method,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        provider_reference=payment.provider_reference,
        instructions=instructions_for(payment, order),
    )


def allowed_actions(payment: Payment) -> list[str]:
    if payment.method == PaymentMethod.STAGING_MOCK:
        return ["refund"] if payment.status == PaymentState.PAID else []
    actions = []
    if payment.status == PaymentState.PENDING:
        actions += ["confirm", "fail"]
    if payment.status == PaymentState.PAID:
        actions.append("refund")
    return actions
