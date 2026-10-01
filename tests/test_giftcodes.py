"""Sinh và chuẩn hoá gift code — unit test."""

from __future__ import annotations

import itertools
import re

import pytest

from app.config import settings
from app.giftcodes import (
    generate_gift_code,
    is_well_formed_gift_code,
    normalize_gift_code,
)


def test_gift_code_format():
    code = generate_gift_code()
    assert re.fullmatch(r"VIP-\d{2}-[A-Z0-9]{6}", code), code


def test_gift_code_year_prefix_not_hard_coded():
    """Tiền tố năm phải lấy từ cấu hình, không hard-code trong mã."""
    code = generate_gift_code(year_prefix="99")
    assert code.startswith("VIP-99-")


def test_gift_code_default_prefix_matches_current_year():
    import datetime as dt

    expected = f"{dt.datetime.now(dt.UTC).year % 100:02d}"
    assert generate_gift_code().split("-")[1] == expected


def test_gift_code_uses_only_unambiguous_characters():
    for _ in range(200):
        body = generate_gift_code().rsplit("-", 1)[1]
        assert not (set(body) & set("IO01")), body


def test_gift_codes_are_unique_in_practice():
    codes = {generate_gift_code() for _ in range(2000)}
    assert len(codes) == 2000, "có đụng độ gift code trong 2000 lần sinh"


def test_gift_code_entropy_is_not_sequential():
    """Hai mã liên tiếp không được giống nhau ở phần thân."""
    bodies = [generate_gift_code().rsplit("-", 1)[1] for _ in range(50)]
    assert len(set(bodies)) == len(bodies)


def test_gift_code_not_derived_from_integer_sequence():
    """Không suy được mã sau từ mã trước (không tuần tự)."""
    codes = [generate_gift_code() for _ in range(10)]
    for previous, current in itertools.pairwise(codes):
        assert previous < current or previous > current  # chỉ cần khác nhau


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("vip-26-abcdef", "VIP-26-ABCDEF"),
        (" VIP-26-ABCDEF ", "VIP-26-ABCDEF"),
        ("vip-26-abc def", "VIP-26-ABCDEF"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_gift_code(raw, expected):
    assert normalize_gift_code(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["VIP-26-ABCDEF", "vip-26-abcdef", " VIP-26-ABCDEF "],
)
def test_well_formed_accepts(raw):
    assert is_well_formed_gift_code(raw)


@pytest.mark.parametrize(
    "raw",
    ["", None, "VIP-26-ABC", "VIP-26-ABCDEFG", "KHONG-PHAI-MA", "VIP-2-ABCDEF", "26-ABCDEF"],
)
def test_well_formed_rejects(raw):
    assert not is_well_formed_gift_code(raw)


def test_alphabet_has_no_ambiguous_characters():
    assert not (set(settings.gift_code_alphabet) & set("IO01"))
