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
    turnstile_secret_key: str | None = None
    turnstile_verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    turnstile_required: bool = False

    # -------------------------------------------------------------------- CORS
    #: Danh sách origin cho phép, phân tách bằng dấu phẩy. RỖNG = không bật CORS.
    cors_allowed_origins: str = ""

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
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

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
