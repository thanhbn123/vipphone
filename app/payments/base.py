"""Giao diện nhà cung cấp thanh toán.

Bốn thao tác bắt buộc (đúng yêu cầu G17):

- `create_payment(db, order)`  — tạo khoản thu cho đơn, trả `Payment`.
- `get_status(payment)`         — trạng thái hiện tại theo nhà cung cấp.
- `verify_webhook(headers, body)` — chữ ký + thời gian hợp lệ? (KHÔNG đụng DB).
- `handle_webhook(db, headers, body)` — xử lý một webhook ĐÃ verify.

Luật: nhà cung cấp KHÔNG tự sửa `orders.payment_status`. Mọi đổi trạng thái đi
qua `app.services.payments.transition()` — đường duy nhất, có vết.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from ..models import Order, Payment


@dataclass(frozen=True)
class WebhookOutcome:
    """Kết quả xử lý webhook. `http_status` là thứ trả về cho nhà cung cấp."""

    outcome: str  # APPLIED | DUPLICATE | REJECTED
    http_status: int
    reason: str | None = None


class PaymentProvider(Protocol):
    method: str
    #: Trạng thái khởi đầu sau `create_payment`.
    initial_status: str

    def create_payment(self, db: Session, order: Order) -> Payment: ...

    def get_status(self, payment: Payment) -> str: ...

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool: ...

    def handle_webhook(
        self, db: Session, headers: Mapping[str, str], body: bytes
    ) -> WebhookOutcome: ...
