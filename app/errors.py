"""Lỗi API có cấu trúc, thống nhất cho toàn ứng dụng."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Lỗi nghiệp vụ trả về JSON có cấu trúc.

    Định dạng:
        {"error": {"code": ..., "message": ..., "fields": {...}}}
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields or {}
        self.headers = headers or {}

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": {"code": self.code, "message": self.message}}
        if self.fields:
            payload["error"]["fields"] = self.fields
        return payload


class ValidationFailed(ApiError):
    def __init__(
        self, fields: dict[str, str], message: str = "Dữ liệu gửi lên không hợp lệ."
    ) -> None:
        super().__init__(422, "VALIDATION_FAILED", message, fields)


class NotFound(ApiError):
    def __init__(self, code: str = "NOT_FOUND", message: str = "Không tìm thấy.") -> None:
        super().__init__(404, code, message)


class RateLimited(ApiError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            429,
            "RATE_LIMITED",
            "Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau.",
            headers={"Retry-After": str(retry_after)},
        )


class StaffAuthNotConfigured(ApiError):
    """Fail CLOSED: chưa cấu hình xác thực thì khoá route, không mở toang."""

    def __init__(self) -> None:
        super().__init__(
            503,
            "STAFF_AUTH_NOT_CONFIGURED",
            "Máy chủ chưa cấu hình xác thực nhân viên (STAFF_API_KEYS). "
            "Khu vực nhân viên tạm đóng.",
        )


class StaffUnauthorized(ApiError):
    def __init__(self) -> None:
        super().__init__(
            401,
            "STAFF_UNAUTHORIZED",
            "Cần khoá truy cập nhân viên hợp lệ.",
            headers={"WWW-Authenticate": "Bearer"},
        )


class SpamRejected(ApiError):
    def __init__(self, detail: str = "Yêu cầu bị coi là spam.") -> None:
        super().__init__(403, "SPAM_REJECTED", detail)


class ExternalServiceUnavailable(ApiError):
    def __init__(self, service: str) -> None:
        super().__init__(
            503,
            "EXTERNAL_SERVICE_UNAVAILABLE",
            f"Không kiểm tra được {service} lúc này. Vui lòng thử lại.",
        )
