"""Che PII khỏi ACCESS LOG của uvicorn.

Access log mặc định ghi NGUYÊN dòng request, gồm query string. Các route quản trị
nhận SĐT/mã tìm kiếm qua query (`/api/admin/orders?q=0912345678`,
`/api/admin/customers?phone=...`) ⇒ SĐT khách nằm trong log máy chủ. Bộ lọc này:

1. Thay GIÁ TRỊ của mọi tham số nhạy cảm bằng `***`.
2. Che MỌI dãy ≥ 9 chữ số còn lại trong đường dẫn (SĐT lọt vào chỗ khác).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qsl, urlencode

SENSITIVE_KEYS = {"phone", "q", "email", "full_name", "name", "address", "token"}
LONG_DIGITS = re.compile(r"\d{9,}")


def redact_path(path: str) -> str:
    base, sep, query = path.partition("?")
    if sep:
        pairs = [
            (key, "***" if key.lower() in SENSITIVE_KEYS else value)
            for key, value in parse_qsl(query, keep_blank_values=True)
        ]
        path = base + "?" + urlencode(pairs, safe="*")
    return LONG_DIGITS.sub(lambda m: "*" * len(m.group(0)), path)


class AccessLogRedactor(logging.Filter):
    """Áp cho logger `uvicorn.access` (args = client, method, path, http_version, status)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            record.args = (args[0], args[1], redact_path(args[2]), args[3], args[4])
        return True


def install() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, AccessLogRedactor) for f in access.filters):
        access.addFilter(AccessLogRedactor())
    install_error_redaction()


# --------------------------------------------------------------------------
# Lỗi database trong log (traceback + thông điệp)
# --------------------------------------------------------------------------
#: PostgreSQL gửi kèm GIÁ TRỊ DÒNG trong DETAIL của lỗi ràng buộc ("Failing row
#: contains (..., <họ tên>, <SĐT>, ...)"). `hide_parameters` của SQLAlchemy KHÔNG
#: che phần này — nó đến từ máy chủ PG. Nên che ở tầng log.
_DB_DETAIL = re.compile(r"(DETAIL:\s*)[^\n]*")
_SQL_PARAMS = re.compile(r"\[parameters: [^\n]*\]")


def redact_text(value: str) -> str:
    value = _DB_DETAIL.sub(r"\1[đã che — có thể chứa dữ liệu khách]", value)
    return _SQL_PARAMS.sub("[parameters: đã che]", value)


class ErrorRedactor(logging.Filter):
    """Che DETAIL/tham số SQL trong thông điệp VÀ traceback trước khi ghi."""

    _formatter = logging.Formatter()

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # log không bao giờ được làm sập request
            return True
        cleaned = redact_text(message)
        if cleaned != message:
            record.msg, record.args = cleaned, ()
        if record.exc_info and not record.exc_text:
            record.exc_text = redact_text(self._formatter.formatException(record.exc_info))
        return True


def install_error_redaction() -> None:
    """Gắn vào MỌI handler đang có: filter của logger không áp cho bản ghi lan từ
    logger con, còn filter của HANDLER thì áp cho mọi bản ghi đi qua nó."""
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            if not any(isinstance(f, ErrorRedactor) for f in handler.filters):
                handler.addFilter(ErrorRedactor())
