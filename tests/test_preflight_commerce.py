"""Preflight staging cho cấu hình THƯƠNG MẠI + hợp đồng `.env.staging.example`.

Hai lỗi thật tìm được khi chuẩn bị deploy staging các gate thương mại:
1. `.env.staging.example` (hợp đồng cấu hình) không có biến nào của G16/G17/ảnh.
2. `MEDIA_ROOT=` (rỗng) bị đọc thành `Path('.')` ⇒ ảnh ghi vào thư mục mã nguồn
   trong container và mất ở lần deploy sau.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.config import REPO_ROOT, Settings

spec = importlib.util.spec_from_file_location(
    "staging_preflight", REPO_ROOT / "scripts" / "staging_preflight.py"
)
preflight = importlib.util.module_from_spec(spec)
# @dataclass cần tìm được module của chính nó trong sys.modules.
sys.modules["staging_preflight"] = preflight
spec.loader.exec_module(preflight)

COMMERCE_KEYS = {
    "RATE_LIMIT_COMMERCE_PER_WINDOW",
    "SHIPPING_FEE_FLAT",
    "MAX_COMMERCE_BODY_BYTES",
    "BANK_TRANSFER_INSTRUCTIONS",
    "PAYMENT_MOCK_WEBHOOK_SECRET",
    "PAYMENT_WEBHOOK_TOLERANCE_SECONDS",
    "MEDIA_ROOT",
    "MAX_IMAGE_BYTES",
}


def run(monkeypatch, env: dict[str, str], app_env="staging"):
    for key in COMMERCE_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    report = preflight.Report()
    preflight.check_commerce(report, app_env)
    return {r.name: (r.status, r.detail) for r in report.results}


def test_env_contract_documents_every_commerce_setting():
    text = (REPO_ROOT / ".env.staging.example").read_text(encoding="utf-8")
    missing = [k for k in COMMERCE_KEYS if k not in text]
    assert missing == []
    # Mọi biến trong hợp đồng phải là trường cấu hình THẬT của ứng dụng.
    fields = {name.upper() for name in Settings.model_fields}
    for key in COMMERCE_KEYS:
        assert key in fields, key


def test_blank_media_root_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("MEDIA_ROOT", "")
    assert Settings().media_root == REPO_ROOT / "var" / "media"
    monkeypatch.setenv("MEDIA_ROOT", "/srv/media")
    assert Settings().media_root == Path("/srv/media")


def test_mock_secret_forbidden_in_production(monkeypatch):
    out = run(monkeypatch, {"PAYMENT_MOCK_WEBHOOK_SECRET": "x" * 64}, app_env="production")
    assert out["PAYMENT_MOCK_WEBHOOK_SECRET không có ở production"][0] == "FAIL"


def test_weak_mock_secret_fails_and_missing_warns(monkeypatch):
    assert (
        run(monkeypatch, {"PAYMENT_MOCK_WEBHOOK_SECRET": "short"})[
            "PAYMENT_MOCK_WEBHOOK_SECRET đủ mạnh"
        ][0]
        == "FAIL"
    )
    assert run(monkeypatch, {})["Webhook giả lập (STAGING_MOCK)"][0] == "WARN"
    assert (
        run(monkeypatch, {"PAYMENT_MOCK_WEBHOOK_SECRET": "y" * 48})[
            "Webhook giả lập (STAGING_MOCK)"
        ][0]
        == "PASS"
    )


@pytest.mark.parametrize(
    "fee, name, status",
    [
        ("abc", "SHIPPING_FEE_FLAT hợp lệ", "FAIL"),
        ("30000.999", "SHIPPING_FEE_FLAT hợp lệ", "FAIL"),
        ("", "Phí giao hàng", "WARN"),
        ("0.00", "Phí giao hàng", "WARN"),
        ("30000", "Phí giao hàng", "PASS"),
    ],
)
def test_shipping_fee_checks(monkeypatch, fee, name, status):
    assert run(monkeypatch, {"SHIPPING_FEE_FLAT": fee})[name][0] == status


def test_relative_media_root_fails(monkeypatch):
    assert (
        run(monkeypatch, {"MEDIA_ROOT": "var/media"})["MEDIA_ROOT là đường dẫn tuyệt đối"][0]
        == "FAIL"
    )


def test_empty_bank_instructions_warn(monkeypatch):
    assert run(monkeypatch, {})["Hướng dẫn chuyển khoản"][0] == "WARN"
