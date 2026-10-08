"""Mọi đường mà `deploy/verify.sh` gọi phải TỒN TẠI trong ứng dụng / repo.

Đã hỏng thật (#88): verify.sh gọi `/assets/css/main.css` và `/api/config` — cả hai
không tồn tại ⇒ nghiệm thu staging KHÔNG BAO GIỜ cấp được phiếu PASS. Lỗi chỉ lộ
ra khi chạy trên máy chủ; test này bắt nó ngay ở máy.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

REPO = Path(__file__).resolve().parents[1]
VERIFY = (REPO / "deploy" / "verify.sh").read_text(encoding="utf-8")
CONF = (REPO / "deploy" / "deploy.conf").read_text(encoding="utf-8")


def _probed_paths() -> list[str]:
    loop = re.search(r'for path in ((?:"[^"]+"\s*)+); do', VERIFY)
    assert loop, "không tìm thấy vòng `for path in ...` trong verify.sh"
    paths = re.findall(r'"([^"]+)"', loop.group(1))
    for key in ("HEALTH_PATH", "READY_PATH"):
        paths.append(re.search(rf"^{key}=(\S+)", CONF, re.M).group(1))
    paths.append("/api/leads")  # smoke POST
    return paths


def _exists(client: TestClient, path: str) -> bool:
    """Đường tồn tại = ứng dụng KHÔNG trả 404 (405 nghĩa là có, sai phương thức)."""
    return client.get(path).status_code != 404


def test_verify_probes_only_existing_paths() -> None:
    with TestClient(app) as client:
        missing = [p for p in _probed_paths() if not _exists(client, p)]
    assert not missing, f"verify.sh gọi đường không tồn tại: {missing}"


def test_negative_control_detects_the_old_broken_paths() -> None:
    """Đối chứng âm: đúng hai đường hỏng cũ phải bị bộ dò coi là KHÔNG tồn tại."""
    with TestClient(app) as client:
        assert not _exists(client, "/api/config")
        assert not _exists(client, "/assets/css/main.css")
