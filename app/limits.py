"""Đọc body có giới hạn.

VÌ SAO CẦN FILE NÀY — một lỗi thật đã đo được ở G08:

Bản trước làm thế này:

    raw = await request.body()                       # đọc HẾT vào RAM
    if len(raw) > settings.max_lead_body_bytes:       # rồi mới kiểm
        raise ApiError(413, ...)

`await request.body()` nạp **toàn bộ** payload vào bộ nhớ rồi mới so với trần,
nên trần 8 KB **không bảo vệ được gì** trước payload lớn: một request 500 MB vẫn
được đệm hết vào RAM trước khi bị từ chối.

Cách sửa: kiểm `Content-Length` **trước**, và với body dạng chunked (không có
`Content-Length`) thì đọc theo từng khối và **bỏ ngay khi vượt trần**.
"""

from __future__ import annotations

from fastapi import Request

from .errors import ApiError


class BodyTooLarge(ApiError):
    def __init__(self) -> None:
        super().__init__(413, "PAYLOAD_TOO_LARGE", "Dữ liệu gửi lên quá lớn.")


class InvalidContentLength(ApiError):
    def __init__(self) -> None:
        super().__init__(400, "INVALID_CONTENT_LENGTH", "Header Content-Length không hợp lệ.")


async def read_limited_body(request: Request, limit: int) -> bytes:
    """Đọc body, không bao giờ vượt `limit` byte.

    - Có `Content-Length`: từ chối NGAY nếu vượt trần, **không đọc một byte nào**.
    - Không có `Content-Length` (chunked): đọc theo khối, vượt là bỏ ngay.
    """
    declared = request.headers.get("content-length")

    if declared is not None:
        try:
            declared_length = int(declared)
        except (TypeError, ValueError) as exc:
            raise InvalidContentLength() from exc

        if declared_length < 0:
            raise InvalidContentLength()

        if declared_length > limit:
            # Điểm mấu chốt: thoát TRƯỚC khi chạm tới body.
            raise BodyTooLarge()

    chunks: list[bytes] = []
    total = 0

    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise BodyTooLarge()
        chunks.append(chunk)

    return b"".join(chunks)
