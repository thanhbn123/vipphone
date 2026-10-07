"""Ba nhà cung cấp của G17: `COD`, `BANK_TRANSFER_MANUAL`, `STAGING_MOCK`.

- **COD**: thu tiền khi giao. Tạo ra là `PENDING` và **KHÔNG BAO GIỜ tự thành
  `PAID`** — chỉ nhân viên xác nhận đã thu, và chỉ khi đơn đã giao đi.
- **BANK_TRANSFER_MANUAL**: chuyển khoản thủ công. `PENDING` cho tới khi nhân
  viên đối soát sao kê và xác nhận. Không có webhook.
- **STAGING_MOCK**: cổng GIẢ LẬP để chứng minh đường webhook (chữ ký, chống
  trùng, idempotent, kiểm số tiền/tiền tệ, khớp đơn/khoản thu, kiểm chuyển trạng
  thái). TẮT ở production dù có khoá.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Order, Payment, PaymentEvent, PaymentMethod, PaymentState
from .base import WebhookOutcome


def _new_payment(order: Order, method: str, status: str, reference: str | None) -> Payment:
    return Payment(
        payment_id=uuid.uuid4(),
        order_id=order.id,
        method=method,
        status=status,
        amount=order.grand_total,
        currency=order.currency,
        provider_reference=reference,
    )


class _NoWebhook:
    """Phương thức thủ công: không có webhook — mọi webhook đều bị từ chối."""

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        return False

    def handle_webhook(
        self, db: Session, headers: Mapping[str, str], body: bytes
    ) -> WebhookOutcome:
        return WebhookOutcome("REJECTED", 404, "NO_WEBHOOK_FOR_METHOD")

    def get_status(self, payment: Payment) -> str:
        return payment.status


class CodProvider(_NoWebhook):
    method = PaymentMethod.COD.value
    initial_status = PaymentState.PENDING.value

    def create_payment(self, db: Session, order: Order) -> Payment:
        return _new_payment(order, self.method, self.initial_status, None)


class BankTransferManualProvider(_NoWebhook):
    method = PaymentMethod.BANK_TRANSFER_MANUAL.value
    initial_status = PaymentState.PENDING.value

    def create_payment(self, db: Session, order: Order) -> Payment:
        # Mã tham chiếu khách ghi vào nội dung chuyển khoản = mã đơn (để đối soát).
        return _new_payment(order, self.method, self.initial_status, None)


# --------------------------------------------------------------------------
# STAGING_MOCK
# --------------------------------------------------------------------------
SIGNATURE_HEADER = "x-mock-signature"
TIMESTAMP_HEADER = "x-mock-timestamp"

#: Trạng thái webhook giả lập được phép báo.
MOCK_EVENT_STATUSES = {"PAID": PaymentState.PAID.value, "FAILED": PaymentState.FAILED.value}


def mock_signature(secret: str, timestamp: str, body: bytes) -> str:
    """HMAC-SHA256(secret, "<timestamp>.<body>") dạng hex — dùng chung cho test/script."""
    message = timestamp.encode("ascii") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


class StagingMockProvider:
    method = PaymentMethod.STAGING_MOCK.value
    initial_status = PaymentState.PENDING.value
    provider_name = "staging-mock"

    def create_payment(self, db: Session, order: Order) -> Payment:
        reference = f"MOCK-{secrets.token_hex(10).upper()}"
        return _new_payment(order, self.method, self.initial_status, reference)

    def get_status(self, payment: Payment) -> str:
        return payment.status

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        secret = settings.payment_mock_webhook_secret
        if not settings.payment_mock_enabled or not secret:
            return False
        signature = headers.get(SIGNATURE_HEADER, "")
        timestamp = headers.get(TIMESTAMP_HEADER, "")
        if not signature or not timestamp.isdigit():
            return False
        if abs(time.time() - int(timestamp)) > settings.payment_webhook_tolerance_seconds:
            return False
        expected = mock_signature(secret, timestamp, body)
        return hmac.compare_digest(expected, signature)

    def handle_webhook(
        self, db: Session, headers: Mapping[str, str], body: bytes
    ) -> WebhookOutcome:
        """Gọi SAU `verify_webhook`. Mọi lối ra đều ghi đúng MỘT `payment_events`."""
        from ..services import payments as payment_service

        try:
            data = json.loads(body)
            event_id = str(data["event_id"])[:128]
            reference = str(data["payment_reference"])[:64]
            reported_status = str(data["status"])
            amount = Decimal(str(data["amount"]))
            currency = str(data["currency"])
        except (ValueError, KeyError, TypeError, InvalidOperation):
            return WebhookOutcome("REJECTED", 400, "MALFORMED_PAYLOAD")
        if not event_id:
            return WebhookOutcome("REJECTED", 400, "MALFORMED_PAYLOAD")

        payload_hash = hashlib.sha256(body).hexdigest()

        # Chống trùng: event_id đã thấy ⇒ trả DUPLICATE, KHÔNG làm gì thêm.
        seen = db.execute(
            select(PaymentEvent).where(
                PaymentEvent.provider == self.provider_name,
                PaymentEvent.provider_event_id == event_id,
            )
        ).scalar_one_or_none()
        if seen is not None:
            return WebhookOutcome("DUPLICATE", 200, None)

        payment = db.execute(
            select(Payment)
            .where(Payment.provider_reference == reference, Payment.method == self.method)
            .with_for_update()
        ).scalar_one_or_none()

        def reject(http_status: int, reason: str) -> WebhookOutcome:
            db.add(
                PaymentEvent(
                    payment_id=payment.id if payment else None,
                    provider=self.provider_name,
                    provider_event_id=event_id,
                    event_type=f"webhook.{reported_status.lower()[:20]}",
                    from_status=payment.status if payment else None,
                    to_status=None,
                    amount=amount,
                    currency=currency[:3],
                    outcome="REJECTED",
                    reason=reason,
                    payload_sha256=payload_hash,
                    actor=f"provider:{self.provider_name}",
                )
            )
            return WebhookOutcome("REJECTED", http_status, reason)

        if payment is None:
            return reject(404, "PAYMENT_NOT_FOUND")
        if reported_status not in MOCK_EVENT_STATUSES:
            return reject(422, "UNKNOWN_STATUS")
        if amount != payment.amount:
            return reject(422, "AMOUNT_MISMATCH")
        if currency != payment.currency:
            return reject(422, "CURRENCY_MISMATCH")

        target = MOCK_EVENT_STATUSES[reported_status]
        if not payment_service.can_transition(payment.status, target):
            return reject(409, "INVALID_TRANSITION")

        try:
            with db.begin_nested():
                payment_service.transition(
                    db,
                    payment,
                    target,
                    actor=f"provider:{self.provider_name}",
                    event_type=f"webhook.{reported_status.lower()}",
                    provider=self.provider_name,
                    provider_event_id=event_id,
                    payload_sha256=payload_hash,
                )
        except IntegrityError:
            # Cùng event_id vừa được một request song song ghi ⇒ trùng.
            return WebhookOutcome("DUPLICATE", 200, None)
        return WebhookOutcome("APPLIED", 200, None)


_PROVIDERS = {
    PaymentMethod.COD.value: CodProvider(),
    PaymentMethod.BANK_TRANSFER_MANUAL.value: BankTransferManualProvider(),
    PaymentMethod.STAGING_MOCK.value: StagingMockProvider(),
}


def method_available(method: str) -> bool:
    if method == PaymentMethod.STAGING_MOCK.value:
        return settings.payment_mock_enabled
    return method in _PROVIDERS


def get_provider(method: str):
    return _PROVIDERS[method]
