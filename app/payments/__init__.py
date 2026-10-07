"""G17 — Lớp thanh toán ĐỘC LẬP nhà cung cấp. Thiết kế: `docs/payments.md`.

Mọi nhà cung cấp hiện thực CÙNG một giao diện (`PaymentProvider`). Thêm một cổng
thật (ngân hàng, ví) sau này = thêm một lớp mới; tầng dịch vụ và đơn hàng không đổi.

Không có tích hợp ngân hàng production nào ở đây.
"""

from __future__ import annotations

from .base import PaymentProvider, WebhookOutcome
from .providers import (
    BankTransferManualProvider,
    CodProvider,
    StagingMockProvider,
    get_provider,
    method_available,
)

__all__ = [
    "BankTransferManualProvider",
    "CodProvider",
    "PaymentProvider",
    "StagingMockProvider",
    "WebhookOutcome",
    "get_provider",
    "method_available",
]
