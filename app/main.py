"""Điểm vào ứng dụng VIP PHONE.

MỘT tiến trình phục vụ cả API lẫn file tĩnh → deploy và rollback đơn giản
(xem docs/adr/0001-stack-selection.md §3.2).
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .config import Settings, get_settings
from .errors import ApiError
from .giftcodes import is_well_formed_gift_code, normalize_gift_code
from .routers import (
    admin,
    admin_customers,
    admin_products,
    catalog,
    gifts,
    health,
    leads,
    products,
    public_config,
)
from .security import apply_security_headers

logger = logging.getLogger("vipphone")

STATIC_PAGES = {
    "/index.html": "index.html",
    "/success.html": "success.html",
    "/redeem.html": "redeem.html",
    #: Vỏ trang quản trị. Bản thân trang KHÔNG chứa dữ liệu — mọi dữ liệu nằm
    #: sau `/api/admin/*` và đều bắt buộc `require_staff`. Trình duyệt không gửi
    #: được header xác thực khi mở một trang HTML, nên chặn ở tầng trang là chặn
    #: nhầm chỗ: nó chỉ làm hỏng trang mà không bảo vệ thêm dữ liệu nào.
    "/admin-leads.html": "admin-leads.html",
    #: G14 — cửa hàng. Vỏ trang KHÔNG chứa dữ liệu: mọi sản phẩm đến từ
    #: `/api/products`. Hard-code sản phẩm vào HTML là thứ bị cấm (xem
    #: `docs/catalog.md` §7.4).
    "/shop": "shop.html",
}


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings)

    app = FastAPI(
        title="VIP PHONE API",
        version=__version__,
        description=(
            "API cho chương trình tặng ốp VIP PHONE: thu lead, cấp gift code, phát quà có audit."
        ),
        docs_url="/docs" if not app_settings.is_production else None,
        redoc_url="/redoc" if not app_settings.is_production else None,
        openapi_url="/openapi.json" if not app_settings.is_production else None,
    )
    app.state.settings = app_settings

    # ---------------------------------------------------------- middleware
    # Chặn Host header lạ (host-header injection / cache poisoning) khi có cấu
    # hình. RỖNG = không giới hạn, và ở production thì readiness BÁO RÕ là chưa
    # cấu hình — không im lặng.
    if app_settings.allowed_host_list:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=app_settings.allowed_host_list)
    elif app_settings.is_production:
        logger.warning("ALLOWED_HOSTS đang RỖNG ở production — máy chủ không giới hạn Host header.")

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        # Mã tương quan cho mọi request: trả về header và để lại trong log, nhờ
        # vậy lần được một sự cố từ phía khách tới đúng dòng log.
        request_id = uuid.uuid4().hex[:16]
        request.state.request_id = request_id

        response = await call_next(request)
        apply_security_headers(response, request.url.path, is_https=request.url.scheme == "https")
        response.headers.setdefault("X-Request-ID", request_id)
        return response

    # ------------------------------------------------------- xử lý ngoại lệ
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_payload(),
            headers=exc.headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = {
            ".".join(str(part) for part in error["loc"]): error.get("msg", "Giá trị không hợp lệ")
            for error in exc.errors()
        }
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_FAILED",
                    "message": "Dữ liệu gửi lên không hợp lệ.",
                    "fields": fields,
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": {
                        "code": f"HTTP_{exc.status_code}",
                        "message": str(exc.detail),
                    }
                },
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}},
        )

    # ------------------------------------------------------------- routers
    app.include_router(health.router)
    app.include_router(public_config.router)
    app.include_router(catalog.router)
    app.include_router(leads.router)
    app.include_router(gifts.router)
    app.include_router(admin.router)
    app.include_router(admin_customers.router)
    app.include_router(products.router)
    app.include_router(admin_products.router)

    # -------------------------------------------------------------- tĩnh
    static_root: Path = app_settings.static_dir

    assets_dir = static_root / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    data_dir = static_root / "data"
    if data_dir.is_dir():
        app.mount("/data", StaticFiles(directory=data_dir), name="data")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_root / "index.html")

    for route_path, filename in STATIC_PAGES.items():

        def make_handler(target: str):
            def handler() -> FileResponse:
                return FileResponse(static_root / target)

            return handler

        app.get(route_path, include_in_schema=False)(make_handler(filename))

    @app.get("/product/{slug}", include_in_schema=False)
    def product_page(slug: str) -> FileResponse:
        """Trang chi tiết sản phẩm.

        Đường dẫn động, nhưng LUÔN trả về đúng một file tĩnh — `slug` KHÔNG bao
        giờ được dùng để ghép đường dẫn file, nên không có đường đi ngược thư mục.
        Slug có tồn tại hay không do `/api/products/{slug}` quyết định ở phía
        trình duyệt; slug sai ⇒ trang hiện "không tìm thấy", KHÔNG hiện hàng giả.
        """
        del slug  # cố ý không dùng để dựng đường dẫn file
        return FileResponse(static_root / "product.html")

    @app.get("/gift/{gift_code}", include_in_schema=False)
    def gift_shortlink(gift_code: str) -> RedirectResponse:
        """Liên kết ngắn cho QR: /gift/VIP-26-XXXXXX → /redeem?code=..."""
        code = normalize_gift_code(gift_code)
        if not is_well_formed_gift_code(code):
            return RedirectResponse(url="/redeem", status_code=302)
        return RedirectResponse(url=f"/redeem?code={code}", status_code=302)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        # HTTP 204 BẮT BUỘC không có body.
        #
        # Bản cũ dùng `JSONResponse(status_code=204, content=None)` — nó VẪN sinh
        # body `null` và đặt Content-Length. Client vẫn nhận 204 (header đã gửi
        # xong trước khi lỗi), nhưng uvicorn ném ở tầng send:
        #   RuntimeError: Response content longer than Content-Length
        # Đo trên staging: 25 request favicon -> ĐÚNG 25 exception trong log.
        # Lỗi VÔ HÌNH với client, và VÔ HÌNH với TestClient vì TestClient không đi
        # qua tầng HTTP của uvicorn.
        return Response(status_code=204)

    logger.info(
        "VIP PHONE khởi động: env=%s, docs=%s, staff_auth=%s",
        app_settings.app_env,
        "on" if not app_settings.is_production else "off",
        "configured" if app_settings.staff_auth_configured else "NOT_CONFIGURED",
    )

    return app


app = create_app()
