"""Chuẩn hoá số điện thoại — unit test (không cần database)."""

from __future__ import annotations

import pytest

from app.phone import is_valid_canonical_phone, is_valid_vn_mobile, normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0912345678", "0912345678"),
        ("+84912345678", "0912345678"),
        ("84912345678", "0912345678"),
        ("0912 345 678", "0912345678"),
        ("0912.345.678", "0912345678"),
        ("0912-345-678", "0912345678"),
        ("  +84 912 345 678  ", "0912345678"),
        ("(09) 1234 5678", "0912345678"),
        ("", ""),
        (None, ""),
        ("abc", ""),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_normalize_phone_is_idempotent():
    once = normalize_phone("+84 912 345 678")
    assert normalize_phone(once) == once


@pytest.mark.parametrize(
    "raw",
    ["0912345678", "+84912345678", "84912345678", "0912 345 678"],
)
def test_same_customer_yields_same_canonical_phone(raw):
    """Cùng một khách, mọi cách viết, phải ra MỘT giá trị.

    Nếu khác nhau thì cùng khách sẽ nhận hai gift code.
    """
    assert normalize_phone(raw) == "0912345678"


@pytest.mark.parametrize(
    "raw",
    [
        "0912345678",  # 09
        "0312345678",  # 03
        "0512345678",  # 05
        "0712345678",  # 07
        "0812345678",  # 08
        "+84912345678",
    ],
)
def test_valid_vn_mobile_accepts(raw):
    assert is_valid_vn_mobile(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "12345",
        "091234567",  # thiếu 1 số
        "09123456789",  # thừa 1 số
        "0212345678",  # 02 không phải đầu số di động
        "0412345678",  # 04
        "0612345678",  # 06
        "0012345678",
        "abcdefghij",
        "",
        None,
    ],
)
def test_valid_vn_mobile_rejects(raw):
    assert not is_valid_vn_mobile(raw)


def test_is_valid_canonical_phone_requires_canonical_form():
    assert is_valid_canonical_phone("0912345678")
    assert not is_valid_canonical_phone("+84912345678")


def test_normalize_phone_truncates_absurd_input():
    """Đầu vào dài bất thường không được tạo ra 'số điện thoại' dài.

    Cột `phone` là String(16); nếu chuỗi hoá ra dài hơn thì sẽ thành lỗi
    tầng database thay vì lỗi kiểm tra đầu vào.
    """
    from app.phone import MAX_NORMALIZED_LENGTH

    raw = "0" * 500 + "912345678"
    normalized = normalize_phone(raw)
    assert len(normalized) <= MAX_NORMALIZED_LENGTH
    # Và đương nhiên nó không phải số hợp lệ.
    assert not is_valid_vn_mobile(raw)
