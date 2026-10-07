"""Kho lưu đối tượng (ảnh sản phẩm). Thiết kế: `docs/product-images.md`.

`ObjectStorage` là ranh giới: hôm nay `LocalFileStorage` (đĩa của máy chủ, phục vụ
qua `/media/...` cùng origin), mai đổi sang kho đối tượng S3-compatible mà không
đổi bảng `product_images` hay API — DB chỉ giữ `storage_key`, không giữ đường dẫn
tuyệt đối hay URL ngoài.

Khoá lưu do MÁY CHỦ sinh (`products/<uuid>.<ext>`), không bao giờ lấy từ tên file
người dùng gửi ⇒ không có đường đi ngược thư mục, không ghi đè file của người khác.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from .config import settings

KEY_RE = re.compile(r"^products/[0-9a-f]{32}\.(png|jpg|webp)$")


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def public_url(self, key: str) -> str: ...


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        if not KEY_RE.match(key):
            raise ValueError("storage key không hợp lệ")
        return self.root / key

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Ghi tệp tạm rồi đổi tên: không bao giờ có ảnh ghi dở được phục vụ ra ngoài.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".up-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def public_url(self, key: str) -> str:
        return f"/media/{key}"


def get_storage() -> ObjectStorage:
    return LocalFileStorage(Path(settings.media_root))
