"""Bảo mật: security header, rate limit, xác thực nhân viên, Turnstile.

Nguyên tắc chung: **fail CLOSED**. Chưa cấu hình thì ĐÓNG, không mở toang.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from collections import deque

import httpx
from fastapi import Request, Response

from .config import settings
from .errors import (
    ExternalServiceUnavailable,
    RateLimited,
    SpamRejected,
    StaffAuthNotConfigured,
    StaffUnauthorized,
)

logger = logging.getLogger("vipphone.security")

# --------------------------------------------------------------------------
# Security header
# --------------------------------------------------------------------------

BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(self)",
    "X-Permitted-Cross-Domain-Policies": "none",
}

#: CSP nghiêm: mọi script/style đều là file ngoài, không có inline.
#: Origin của Cloudflare Turnstile. CHỈ được thêm vào CSP khi Turnstile BẬT.
TURNSTILE_ORIGIN = "https://challenges.cloudflare.com"


def build_strict_csp(*, turnstile: bool) -> str:
    """CSP nghiêm, và CHỈ mở cho Cloudflare khi Turnstile thật sự bật.

    Vì sao phải có điều kiện: CSP là hàng rào. Mở sẵn cho một origin bên thứ ba
    khi tính năng CHƯA dùng là nới rào mà không đổi lại lợi ích gì. Khi tắt
    Turnstile, CSP phải quay về đúng `script-src 'self'`.
    """
    script_src = "'self'"
    frame_src = ""
    if turnstile:
        script_src = f"'self' {TURNSTILE_ORIGIN}"
        # Widget Turnstile render trong iframe của Cloudflare.
        frame_src = f"frame-src {TURNSTILE_ORIGIN}; "

    return (
        "default-src 'self'; "
        f"script-src {script_src}; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        f"{frame_src}"
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "object-src 'none'"
    )


#: CSP dùng khi Turnstile TẮT (mặc định). Giữ tên cũ để không phá chỗ đang dùng.
STRICT_CSP = build_strict_csp(turnstile=False)

#: CSP nới cho trang tài liệu API tự sinh (Swagger UI cần inline + CDN).
DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)

_DOCS_PREFIXES = ("/docs", "/redoc", "/openapi.json")


def is_docs_path(path: str) -> bool:
    return path.startswith(_DOCS_PREFIXES)


def apply_security_headers(response: Response, path: str, *, is_https: bool) -> None:
    for name, value in BASE_SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)

    csp = DOCS_CSP if is_docs_path(path) else build_strict_csp(turnstile=settings.turnstile_enabled)
    response.headers.setdefault("Content-Security-Policy", csp)

    if is_https:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )

    # Trang HTML không được cache để tránh lộ dữ liệu qua proxy trung gian.
    if not path.startswith(("/assets/", "/data/")):
        response.headers.setdefault("Cache-Control", "no-store")


# --------------------------------------------------------------------------
# Rate limit (cửa sổ trượt, trong bộ nhớ tiến trình)
# --------------------------------------------------------------------------


class SlidingWindowRateLimiter:
    """Giới hạn tần suất theo cửa sổ trượt, giữ trong bộ nhớ.

    GIỚI HẠN ĐÃ BIẾT: bộ đếm nằm trong tiến trình. Chạy nhiều worker/instance
    thì mỗi tiến trình đếm riêng, nên giới hạn thực tế = limit * số instance.
    Muốn chính xác khi scale ngang phải dùng Redis. Ghi rõ ở docs/MASTER_STATUS.md,
    KHÔNG giả vờ là đủ cho production nhiều instance.
    """

    def __init__(self, limit: int, window_seconds: int, max_keys: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, *, now: float | None = None) -> tuple[bool, int]:
        """Trả (cho_phép, retry_after_giây)."""
        if self.limit <= 0:
            return True, 0

        moment = time.monotonic() if now is None else now
        cutoff = moment - self.window

        with self._lock:
            bucket = self._hits.get(key)
            if bucket is None:
                if len(self._hits) >= self.max_keys:
                    self._evict_oldest()
                bucket = deque()
                self._hits[key] = bucket

            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self.limit:
                retry_after = max(1, int(bucket[0] + self.window - moment) + 1)
                return False, retry_after

            bucket.append(moment)
            return True, 0

    def _evict_oldest(self) -> None:
        """Bỏ khoá ít được dùng gần đây nhất khi vượt trần bộ nhớ."""
        oldest_key = None
        oldest_time = float("inf")
        for key, bucket in self._hits.items():
            last = bucket[-1] if bucket else 0.0
            if last < oldest_time:
                oldest_time = last
                oldest_key = key
        if oldest_key is not None:
            self._hits.pop(oldest_key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


lead_rate_limiter = SlidingWindowRateLimiter(
    limit=settings.rate_limit_leads_per_window,
    window_seconds=settings.rate_limit_window_seconds,
    max_keys=settings.rate_limit_max_keys,
)


def client_ip(request: Request) -> str:
    """Địa chỉ dùng làm khoá rate limit.

    Mặc định lấy `request.client.host`. CHỈ tin `X-Forwarded-For` khi
    `TRUST_PROXY_HEADERS=true`, vì header đó do client tự đặt được.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_lead_rate_limit(request: Request) -> None:
    if not settings.rate_limit_enabled:
        return
    allowed, retry_after = lead_rate_limiter.check(client_ip(request))
    if not allowed:
        raise RateLimited(retry_after)


# --------------------------------------------------------------------------
# Xác thực nhân viên
# --------------------------------------------------------------------------


def _actor_label(api_key: str) -> str:
    """Nhãn định danh khoá mà KHÔNG lộ khoá."""
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
    return f"staff:{digest}"


def _extract_staff_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    header_key = request.headers.get("x-staff-key", "").strip()
    return header_key or None


def optional_staff(request: Request) -> str | None:
    """Như `require_staff` nhưng KHÔNG ném lỗi — trả None nếu không có quyền.

    Dùng cho endpoint vừa phục vụ công khai vừa có phần chi tiết dành cho nhân
    viên (ví dụ `/api/ready`): công khai thấy ít, nhân viên thấy đủ.
    """
    configured = settings.staff_key_set
    if not configured:
        return None

    token = _extract_staff_token(request)
    if not token:
        return None

    for candidate in configured:
        if secrets.compare_digest(token, candidate):
            return _actor_label(candidate)

    return None


def require_staff(request: Request) -> str:
    """Dependency FastAPI. Trả nhãn actor khi hợp lệ, ném lỗi khi không."""
    configured = settings.staff_key_set

    if not configured:
        # Fail CLOSED — tuyệt đối không cho qua khi chưa cấu hình.
        raise StaffAuthNotConfigured()

    token = _extract_staff_token(request)
    if not token:
        raise StaffUnauthorized()

    for candidate in configured:
        if secrets.compare_digest(token, candidate):
            return _actor_label(candidate)

    logger.warning("Xác thực nhân viên thất bại từ %s", client_ip(request))
    raise StaffUnauthorized()


# --------------------------------------------------------------------------
# Turnstile (adapter — KHÔNG commit secret)
# --------------------------------------------------------------------------


def turnstile_configured() -> bool:
    return bool(settings.turnstile_secret_key)


async def verify_turnstile(
    token: str | None, remote_ip: str | None, *, client: httpx.AsyncClient | None = None
) -> None:
    """Kiểm tra token Turnstile nếu máy chủ ĐÃ cấu hình secret.

    Chưa cấu hình thì bỏ qua (ghi rõ trạng thái ở `/api/ready`), trừ khi
    `TURNSTILE_REQUIRED=true` — lúc đó từ chối để tránh hở im lặng.
    """
    if not turnstile_configured():
        if settings.turnstile_required:
            raise SpamRejected("Máy chủ yêu cầu Turnstile nhưng chưa cấu hình secret.")
        return

    if not token:
        raise SpamRejected("Thiếu token chống spam.")

    payload = {"secret": settings.turnstile_secret_key, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=5.0)
    try:
        response = await http.post(settings.turnstile_verify_url, data=payload)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("Turnstile không phản hồi: %s", exc)
        raise ExternalServiceUnavailable("Turnstile") from exc
    finally:
        if owns_client:
            await http.aclose()

    if not data.get("success"):
        raise SpamRejected("Không qua được kiểm tra chống spam.")
