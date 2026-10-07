"""G16 — API CÔNG KHAI giỏ hàng, checkout, tra đơn. Thiết kế: `docs/commerce.md`.

Ranh giới:

- Giỏ/đơn chỉ truy cập được bằng token sở hữu (`X-Cart-Token` / `X-Order-Token`).
  Sai/thiếu token ⇒ **404** giống hệt "không tồn tại" (chống IDOR + chống dò).
- Không có trường nào nhận giá/tổng tiền để TÍNH. Máy chủ tự tính.
- Checkout BẮT BUỘC `Idempotency-Key`. Thiếu khoá ⇒ 400 — không đoán hộ, vì đoán
  hộ là mở đường cho double-submit tạo hai đơn.
- Không dùng cookie ⇒ không có bề mặt CSRF: trình duyệt khác origin không tự gửi
  được header token, và CORS chỉ mở cho origin đã khai.
"""

from __future__ import annotations

import json
import re
import uuid

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiError, ValidationFailed
from ..limits import read_limited_body
from ..schemas import (
    CartCreatedOut,
    CartItemAddRequest,
    CartItemUpdateRequest,
    CartOut,
    CheckoutOut,
    CheckoutRequest,
    OrderOut,
    _clean_sku,
)
from ..security import enforce_commerce_rate_limit
from ..services import commerce, inventory
from ..services import payments as payment_service
from .leads import _field_errors

router = APIRouter(prefix="/api", tags=["commerce"])

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

#: Hook chạy TRONG giao dịch checkout, theo THỨ TỰ. Hook ném lỗi ⇒ cả đơn rollback.
#: Kho giữ hàng TRƯỚC (thiếu hàng thì không tạo khoản thu vô ích), rồi G17 tạo khoản thu.
CHECKOUT_HOOKS: list = [inventory.checkout_hook, payment_service.checkout_hook]

#: Huỷ đơn ⇒ nhả hàng giữ + huỷ khoản thu đang chờ; giao đi ⇒ trừ kho.
for _hook in (inventory.on_order_status, payment_service.on_order_status):
    if _hook not in commerce.STATUS_HOOKS:
        commerce.STATUS_HOOKS.append(_hook)


async def _parse(request: Request, model: type[BaseModel]):
    raw = await read_limited_body(request, request.app.state.settings.max_commerce_body_bytes)
    try:
        body = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise ApiError(400, "INVALID_JSON", "Body không phải JSON hợp lệ.") from exc
    if not isinstance(body, dict):
        raise ApiError(400, "INVALID_JSON", "Body phải là một đối tượng JSON.")
    try:
        return model.model_validate(body)
    except ValidationError as exc:
        raise ValidationFailed(_field_errors(exc)) from exc


def _sku_path(sku: str) -> str:
    try:
        return _clean_sku(sku)
    except ValueError as exc:
        raise ApiError(404, "CART_ITEM_NOT_FOUND", "Sản phẩm này không có trong giỏ.") from exc


# ------------------------------------------------------------------- giỏ hàng
@router.post("/cart", response_model=CartCreatedOut, status_code=status.HTTP_201_CREATED)
def create_cart(request: Request, db: Session = Depends(get_db)) -> CartCreatedOut:
    enforce_commerce_rate_limit(request)
    cart, token = commerce.create_cart(db)
    db.commit()
    view = commerce.serialize_cart(db, cart)
    return CartCreatedOut(**view.model_dump(), cart_token=token)


@router.get("/cart/{cart_id}", response_model=CartOut)
def get_cart(
    cart_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_cart_token: str | None = Header(default=None),
) -> CartOut:
    cart = commerce.get_owned_cart(db, cart_id, x_cart_token)
    return commerce.serialize_cart(db, cart)


@router.post("/cart/{cart_id}/items", response_model=CartOut)
async def add_cart_item(
    cart_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    x_cart_token: str | None = Header(default=None),
) -> CartOut:
    payload: CartItemAddRequest = await _parse(request, CartItemAddRequest)
    cart = commerce.get_owned_cart(db, cart_id, x_cart_token, lock=True)
    commerce.add_item(db, cart, payload.sku, payload.quantity)
    db.commit()
    return commerce.serialize_cart(db, cart)


@router.patch("/cart/{cart_id}/items/{sku}", response_model=CartOut)
async def update_cart_item(
    cart_id: uuid.UUID,
    sku: str,
    request: Request,
    db: Session = Depends(get_db),
    x_cart_token: str | None = Header(default=None),
) -> CartOut:
    payload: CartItemUpdateRequest = await _parse(request, CartItemUpdateRequest)
    cart = commerce.get_owned_cart(db, cart_id, x_cart_token, lock=True)
    commerce.update_item(db, cart, _sku_path(sku), payload.quantity)
    db.commit()
    return commerce.serialize_cart(db, cart)


@router.delete("/cart/{cart_id}/items/{sku}", response_model=CartOut)
def remove_cart_item(
    cart_id: uuid.UUID,
    sku: str,
    db: Session = Depends(get_db),
    x_cart_token: str | None = Header(default=None),
) -> CartOut:
    cart = commerce.get_owned_cart(db, cart_id, x_cart_token, lock=True)
    commerce.remove_item(db, cart, _sku_path(sku))
    db.commit()
    return commerce.serialize_cart(db, cart)


# ------------------------------------------------------------------- checkout
@router.post("/checkout", response_model=CheckoutOut, status_code=status.HTTP_201_CREATED)
async def checkout(
    request: Request,
    db: Session = Depends(get_db),
    x_cart_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> CheckoutOut:
    enforce_commerce_rate_limit(request)
    if not idempotency_key or not IDEMPOTENCY_KEY_RE.match(idempotency_key):
        raise ApiError(
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Thiếu hoặc sai header Idempotency-Key (16-128 ký tự chữ/số/-/_).",
        )
    payload: CheckoutRequest = await _parse(request, CheckoutRequest)
    result = commerce.checkout(
        db,
        payload,
        idempotency_key=idempotency_key,
        token=x_cart_token,
        hooks=tuple(CHECKOUT_HOOKS),
    )
    view = commerce.serialize_order(db, result.order)
    view.payment = payment_service.public_payment(db, result.order)
    return CheckoutOut(**view.model_dump(), replayed=result.replayed)


# --------------------------------------------------------------- tra đơn
@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_order_token: str | None = Header(default=None),
) -> OrderOut:
    order = commerce.get_owned_order(db, order_id, x_order_token)
    view = commerce.serialize_order(db, order)
    view.payment = payment_service.public_payment(db, order)
    return view
