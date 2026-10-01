"""Health check (liveness) và readiness."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import __version__
from ..config import settings
from ..db import get_db
from ..security import optional_staff, turnstile_configured

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", summary="Liveness — không truy vấn database")
def health() -> dict:
    """Chỉ nói tiến trình còn sống. Không phụ thuộc database."""
    return {
        "status": "ok",
        "service": "vipphone",
        "version": __version__,
        "env": settings.app_env,
    }


@router.get("/ready", summary="Readiness — có kiểm tra database và cấu hình")
def ready(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """Trả 200 khi sẵn sàng phục vụ, 503 khi chưa.

    ⚠️  CÔNG KHAI CHỈ THẤY `status`. Phần chi tiết (migration head, turnstile,
    staff auth, phiên bản) là **thông tin trinh sát**: nó cho kẻ tấn công biết
    chính xác bot protection đang tắt và schema đang ở đâu. Chi tiết chỉ trả khi
    người gọi có khoá nhân viên hợp lệ, hoặc khi bật tường minh
    `EXPOSE_READINESS_DETAILS=true`.
    """
    actor = optional_staff(request)
    checks: dict[str, object] = {}

    database_ok = True
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        database_ok = False
        checks["database"] = f"error: {type(exc).__name__}"

    migration_head = None
    if database_ok:
        try:
            migration_head = db.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar()
            checks["migration_head"] = migration_head or "none"
        except Exception:
            checks["migration_head"] = "not_migrated"

    checks["staff_auth"] = "configured" if settings.staff_auth_configured else "NOT_CONFIGURED"
    checks["turnstile"] = "configured" if turnstile_configured() else "NOT_CONFIGURED"
    checks["rate_limit"] = "on" if settings.rate_limit_enabled else "OFF"
    checks["allowed_hosts"] = "configured" if settings.allowed_host_list else "NOT_CONFIGURED"

    is_ready = database_ok
    if not is_ready:
        response.status_code = 503

    public: dict = {"status": "ready" if is_ready else "not_ready"}

    if actor is not None or settings.expose_readiness_details:
        public |= {
            "env": settings.app_env,
            "version": __version__,
            "checks": checks,
        }

    return public
