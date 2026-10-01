"""Cấu hình ứng dụng VIP PHONE.

Mọi giá trị đọc từ biến môi trường (hoặc file `.env` khi chạy máy).
KHÔNG có secret nào được đặt mặc định trong mã nguồn.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["dev", "test", "staging", "production"]

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Alphabet bỏ các ký tự dễ nhầm khi đọc/gõ: I, O, 0, 1.
DEFAULT_GIFT_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- môi trường
    app_env: AppEnv = "dev"
    log_level: str = "INFO"

    # ------------------------------------------------------------------ dữ liệu
    database_url: str = "postgresql+psycopg://vipphone:vipphone@localhost:5432/vipphone"
    sql_echo: bool = False

    # -------------------------------------------------------------- địa chỉ công khai
    #: Dùng để dựng URL trong mã QR. KHÔNG hard-code domain production trong mã nguồn.
    public_base_url: str = "http://localhost:8000"

    # --------------------------------------------------------------- gift code
    #: Tiền tố 2 chữ số của năm. Để trống thì suy từ năm hiện tại (UTC).
    gift_code_year_prefix: str | None = None
    gift_code_alphabet: str = DEFAULT_GIFT_ALPHABET
    gift_code_length: int = Field(default=6, ge=4, le=12)
    gift_code_max_attempts: int = Field(default=8, ge=1, le=50)

    # ------------------------------------------------------------ xác thực nhân viên
    #: Danh sách khoá API nhân viên, phân tách bằng dấu phẩy.
    #: RỖNG = chưa cấu hình = các route nhân viên trả 503 (fail closed, KHÔNG fail open).
    staff_api_keys: str = ""

    # -------------------------------------------------------------- chống lạm dụng
    rate_limit_enabled: bool = True
    rate_limit_leads_per_window: int = Field(default=10, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    #: Số cửa sổ giữ trong bộ nhớ cho mỗi khoá.
    rate_limit_max_keys: int = Field(default=10_000, ge=100)
    #: Chỉ bật khi máy chủ THẬT SỰ nằm sau reverse proxy tin cậy.
    #: Bật sai chỗ cho phép kẻ tấn công giả `X-Forwarded-For` để né rate limit.
    trust_proxy_headers: bool = False

    # --------------------------------------------------------------- turnstile
    #: Để trống = tắt. KHÔNG commit secret thật.
    #: Khoá SECRET — chỉ ở server, KHÔNG bao giờ lộ ra client.
    turnstile_secret_key: str | None = None
    #: Khoá SITE — CÔNG KHAI theo thiết kế của Cloudflare (nằm trong HTML/JS).
    #: Đây không phải secret; nhưng cũng không đưa vào repo dưới dạng giá trị thật.
    turnstile_site_key: str | None = None
    turnstile_verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    turnstile_required: bool = False

    # -------------------------------------------------------------------- CORS
    #: CỐ Ý KHÔNG CÓ CẤU HÌNH CORS.
    #:
    #: Trước đây có `CORS_ALLOWED_ORIGINS` nhưng **không chỗ nào dùng** — cấu
    #: hình an ninh đọc như đã làm mà thực ra chưa làm, tệ hơn cả không có.
    #: API và frontend phục vụ CÙNG ORIGIN nên CORS không cần thiết. Nếu sau này
    #: tách frontend sang origin khác thì phải gắn `CORSMiddleware` với allowlist
    #: TƯỜNG MINH (không `*`, không `allow_credentials`), và viết test cho nó.

    # ------------------------------------------------------------------ host
    #: Danh sách Host được phép, phân tách bằng dấu phẩy. RỖNG = không giới hạn Host.
    #: Đặt giá trị thật khi chạy sau proxy để chặn host-header injection.
    allowed_hosts: str = ""

    #: Có công khai chi tiết của `/api/ready` (migration head, turnstile, ...) không.
    #: Mặc định TẮT: chi tiết chỉ dành cho nhân viên. Bật chỉ khi có lý do.
    expose_readiness_details: bool = False

    # ------------------------------------------------------------------ giới hạn
    max_lead_body_bytes: int = Field(default=8_192, ge=1024)

    # ---------------------------------------------------------------- đường dẫn
    static_dir: Path = REPO_ROOT

    @field_validator("gift_code_alphabet")
    @classmethod
    def _check_alphabet(cls, value: str) -> str:
        unique = "".join(dict.fromkeys(value))
        if len(unique) < 16:
            raise ValueError("gift_code_alphabet phải có ít nhất 16 ký tự khác nhau")
        return unique

    @field_validator("public_base_url")
    @classmethod
    def _check_base_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("public_base_url phải bắt đầu bằng http:// hoặc https://")
        return cleaned

    # -------------------------------------------------------------- tiện ích
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def staff_key_set(self) -> frozenset[str]:
        """Tập khoá API nhân viên đã cấu hình (đã bỏ khoảng trắng rỗng)."""
        return frozenset(part.strip() for part in self.staff_api_keys.split(",") if part.strip())

    @property
    def staff_auth_configured(self) -> bool:
        return len(self.staff_key_set) > 0

    @property
    def turnstile_secret_configured(self) -> bool:
        return bool(self.turnstile_secret_key)

    @property
    def turnstile_enabled(self) -> bool:
        """Turnstile có ĐỦ điều kiện để chạy end-to-end không.

        Cần CẢ HAI: khoá site (để frontend render widget) và khoá secret (để server
        xác minh). Thiếu một trong hai thì widget không hoạt động được — và nếu
        `TURNSTILE_REQUIRED=true` ở trạng thái đó thì mọi lead bị chặn.

        Trạng thái này được `/api/public-config` trả cho frontend, và được
        `scripts/staging_preflight.sh` kiểm.
        """
        return bool(self.turnstile_site_key) and bool(self.turnstile_secret_key)

    @property
    def allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def year_prefix(self) -> str:
        """Tiền tố năm của gift code — KHÔNG hard-code."""
        if self.gift_code_year_prefix:
            digits = "".join(ch for ch in self.gift_code_year_prefix if ch.isdigit())
            if not digits:
                raise ValueError("gift_code_year_prefix phải chứa chữ số")
            return digits[-2:].zfill(2)
        return f"{dt.datetime.now(dt.UTC).year % 100:02d}"

    def redeem_url(self, gift_code: str) -> str:
        """URL công khai duy nhất được nhúng vào mã QR. Không chứa PII."""
        return f"{self.public_base_url}/redeem?code={gift_code}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
