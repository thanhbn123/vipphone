"""Cấu hình CÔNG KHAI cho frontend.

Endpoint này trả những gì trình duyệt CẦN BIẾT để hoạt động — và **tuyệt đối không**
trả secret.

Vì sao cần: trước đây frontend phải hard-code mọi thứ, nên không thể "bật Turnstile
qua biến môi trường" — bật cờ ở server thì widget vẫn không xuất hiện, và mọi lead
bị chặn 403 mà không ai hiểu vì sao. Endpoint này nối đúng chỗ đó.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..payments import method_available

PAYMENT_METHOD_ORDER = ("COD", "BANK_TRANSFER_MANUAL", "STAGING_MOCK")

router = APIRouter(prefix="/api", tags=["config"])


class TurnstilePublicConfig(BaseModel):
    #: `True` chỉ khi có ĐỦ khoá site + secret. Thiếu một trong hai ⇒ `False`,
    #: vì widget không chạy được và bật cờ required sẽ chặn hết lead.
    enabled: bool
    #:: Khoá SITE là khoá CÔNG KHAI theo thiết kế Cloudflare. Khoá SECRET không bao
    #: giờ xuất hiện ở bất kỳ response nào — có test khẳng định điều đó.
    site_key: str | None = None
    #: Nói thẳng ra khi cấu hình nửa vời, để người vận hành biết mình đang ở đâu.
    warning: str | None = None


class PublicConfigResponse(BaseModel):
    turnstile: TurnstilePublicConfig
    #: G17 — phương thức thanh toán ĐANG DÙNG ĐƯỢC (thứ tự hiển thị). `STAGING_MOCK`
    #: chỉ có mặt khi máy chủ bật giả lập (không bao giờ ở production).
    payment_methods: list[str] = []


@router.get(
    "/public-config",
    response_model=PublicConfigResponse,
    summary="Cấu hình công khai cho frontend (KHÔNG chứa secret)",
)
def public_config() -> PublicConfigResponse:
    has_site = bool(settings.turnstile_site_key)
    has_secret = settings.turnstile_secret_configured

    warning: str | None = None
    if settings.turnstile_required and not (has_site and has_secret):
        warning = (
            "TURNSTILE_REQUIRED=true nhưng thiếu khoá site hoặc khoá secret — "
            "mọi lead sẽ bị từ chối cho tới khi cấu hình đủ."
        )
    elif has_secret != has_site:
        warning = (
            "Cấu hình Turnstile chưa đủ cặp: cần CẢ khoá site (cho frontend) và "
            "khoá secret (cho server). Hiện chỉ có một trong hai."
        )

    return PublicConfigResponse(
        turnstile=TurnstilePublicConfig(
            enabled=settings.turnstile_enabled,
            site_key=settings.turnstile_site_key if settings.turnstile_enabled else None,
            warning=warning,
        ),
        payment_methods=[m for m in PAYMENT_METHOD_ORDER if method_available(m)],
    )
