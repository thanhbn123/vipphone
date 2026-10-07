"""G16 — Giỏ hàng, checkout, đơn hàng. Thiết kế: `docs/commerce.md`.

Năm luật của file này:

1. **Máy chủ giữ giá.** Tổng tiền tính từ `product_variants.sale_price` hiện
   hành lúc đặt, bằng `Decimal`. Không có tham số nào nhận giá từ client.
2. **Quyền sở hữu bằng token bí mật.** Giỏ/đơn chỉ đọc-ghi được khi có token
   (máy chủ giữ SHA-256). Sai token ⇒ **404**, không phải 403: 403 xác nhận rằng
   giỏ đó CÓ tồn tại — tức là cho kẻ dò một phép thử.
3. **Checkout idempotent ở TẦNG DB.** `orders.idempotency_key` UNIQUE và
   `orders.cart_id` UNIQUE. Giỏ bị khoá `SELECT … FOR UPDATE` trong suốt checkout
   ⇒ hai checkout đồng thời của cùng giỏ xếp hàng; người sau thấy giỏ đã
   `CHECKED_OUT` và nhận lại đơn đã có. Đúng MỘT đơn, kể cả khi khoá khác nhau.
4. **Ảnh chụp giá.** `order_items.unit_price` chụp giá lúc đặt; đổi giá SKU sau
   đó không đụng tới đơn cũ.
5. **Chuyển trạng thái chỉ qua `change_order_status` / `set_payment_status`.**
   Mọi lần chuyển ghi một dòng `order_status_events`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..errors import ApiError, NotFound
from ..models import (
    Cart,
    CartItem,
    CartStatus,
    Customer,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusEvent,
    PaymentStatus,
    Product,
    ProductVariant,
    ShippingAddress,
)
from ..schemas import (
    CartItemOut,
    CartOut,
    CheckoutRequest,
    OrderItemOut,
    OrderOut,
)
from .customers import find_or_create_customer_by_contact
from .gifts import mask_phone

logger = logging.getLogger("vipphone.commerce")

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

#: Chuyển trạng thái đơn HỢP LỆ. Trạng thái cuối (`COMPLETED`, `CANCELLED`) không đi đâu nữa.
ORDER_TRANSITIONS: dict[str, frozenset[str]] = {
    OrderStatus.DRAFT: frozenset({OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED}),
    OrderStatus.PENDING_PAYMENT: frozenset({OrderStatus.CONFIRMED, OrderStatus.CANCELLED}),
    OrderStatus.CONFIRMED: frozenset({OrderStatus.PROCESSING, OrderStatus.CANCELLED}),
    OrderStatus.PROCESSING: frozenset({OrderStatus.SHIPPED, OrderStatus.CANCELLED}),
    OrderStatus.SHIPPED: frozenset({OrderStatus.COMPLETED}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}

#: Chuyển trạng thái THANH TOÁN hợp lệ — chỉ tầng dịch vụ thanh toán (G17) gọi.
PAYMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    PaymentStatus.UNPAID: frozenset({PaymentStatus.PENDING, PaymentStatus.PAID}),
    PaymentStatus.PENDING: frozenset(
        {PaymentStatus.PAID, PaymentStatus.FAILED, PaymentStatus.UNPAID}
    ),
    PaymentStatus.FAILED: frozenset({PaymentStatus.PENDING}),
    PaymentStatus.PAID: frozenset({PaymentStatus.REFUNDED}),
    PaymentStatus.REFUNDED: frozenset(),
}


# --------------------------------------------------------------------------
# Token sở hữu
# --------------------------------------------------------------------------
def new_owner_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str | None, expected_hash: str) -> bool:
    if not token:
        return False
    return hmac.compare_digest(hash_token(token), expected_hash)


# --------------------------------------------------------------------------
# Giỏ hàng
# --------------------------------------------------------------------------
def create_cart(db: Session) -> tuple[Cart, str]:
    token = new_owner_token()
    cart = Cart(cart_id=uuid.uuid4(), owner_token_hash=hash_token(token), status="ACTIVE")
    db.add(cart)
    db.flush()
    return cart, token


def get_owned_cart(
    db: Session, cart_id: uuid.UUID, token: str | None, *, lock: bool = False
) -> Cart:
    """Giỏ của CHÍNH chủ. Không có / sai token ⇒ CÙNG một lỗi 404."""
    stmt = select(Cart).where(Cart.cart_id == cart_id)
    if lock:
        stmt = stmt.with_for_update()
    cart = db.execute(stmt).scalar_one_or_none()
    if cart is None or not token_matches(token, cart.owner_token_hash):
        raise NotFound("CART_NOT_FOUND", "Không tìm thấy giỏ hàng.")
    return cart


def _require_active(cart: Cart) -> None:
    if cart.status != CartStatus.ACTIVE:
        raise ApiError(409, "CART_NOT_ACTIVE", "Giỏ hàng này đã đặt hàng xong, không sửa được.")


def _sellable_variant(db: Session, sku: str) -> ProductVariant:
    """SKU bán được = SKU active VÀ sản phẩm active. Không thì 404 như không tồn tại."""
    row = db.execute(
        select(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            ProductVariant.sku == sku,
            ProductVariant.active.is_(True),
            Product.active.is_(True),
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFound("SKU_NOT_AVAILABLE", "Sản phẩm này hiện không bán.")
    return row


def add_item(db: Session, cart: Cart, sku: str, quantity: int) -> None:
    _require_active(cart)
    variant = _sellable_variant(db, sku)
    item = db.execute(
        select(CartItem).where(CartItem.cart_id == cart.id, CartItem.sku_id == variant.id)
    ).scalar_one_or_none()
    if item is None:
        db.add(CartItem(cart_id=cart.id, sku_id=variant.id, quantity=quantity))
    else:
        new_quantity = item.quantity + quantity
        if new_quantity > 99:
            raise ApiError(
                422,
                "QUANTITY_TOO_LARGE",
                "Mỗi sản phẩm tối đa 99 cái trong một giỏ.",
                fields={"quantity": "Tối đa 99."},
            )
        item.quantity = new_quantity
    db.flush()


def _cart_item_for_sku(db: Session, cart: Cart, sku: str) -> CartItem:
    item = db.execute(
        select(CartItem)
        .join(ProductVariant, ProductVariant.id == CartItem.sku_id)
        .where(CartItem.cart_id == cart.id, ProductVariant.sku == sku)
    ).scalar_one_or_none()
    if item is None:
        raise NotFound("CART_ITEM_NOT_FOUND", "Sản phẩm này không có trong giỏ.")
    return item


def update_item(db: Session, cart: Cart, sku: str, quantity: int) -> None:
    _require_active(cart)
    _cart_item_for_sku(db, cart, sku).quantity = quantity
    db.flush()


def remove_item(db: Session, cart: Cart, sku: str) -> None:
    _require_active(cart)
    db.delete(_cart_item_for_sku(db, cart, sku))
    db.flush()


@dataclass(frozen=True)
class PricedLine:
    variant: ProductVariant
    product: Product
    quantity: int
    available: bool

    @property
    def unit_price(self) -> Decimal:
        return self.variant.sale_price

    @property
    def line_total(self) -> Decimal:
        return (self.variant.sale_price * self.quantity).quantize(CENT)


def priced_lines(db: Session, cart: Cart) -> list[PricedLine]:
    """Dòng giỏ + GIÁ HIỆN HÀNH từ DB. Thứ tự xác định theo id dòng giỏ."""
    rows = db.execute(
        select(CartItem, ProductVariant, Product)
        .join(ProductVariant, ProductVariant.id == CartItem.sku_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(CartItem.cart_id == cart.id)
        .order_by(CartItem.id.asc())
    ).all()
    return [
        PricedLine(
            variant=variant,
            product=product,
            quantity=item.quantity,
            available=bool(variant.active and product.active),
        )
        for item, variant, product in rows
    ]


def shipping_fee_for(subtotal: Decimal) -> Decimal:
    """Phí giao hàng. MỘT hàm cho cả giỏ lẫn checkout — hai nơi tính khác nhau
    thì `expected_total` của khách sẽ luôn lệch và mọi đơn bị từ chối."""
    if subtotal <= ZERO:
        return ZERO
    return Decimal(settings.shipping_fee_flat).quantize(CENT)


def serialize_cart(db: Session, cart: Cart) -> CartOut:
    lines = priced_lines(db, cart)
    subtotal = sum((line.line_total for line in lines if line.available), ZERO).quantize(CENT)
    shipping_fee = shipping_fee_for(subtotal)
    return CartOut(
        cart_id=cart.cart_id,
        status=cart.status,
        currency=cart.currency,
        items=[
            CartItemOut(
                sku=line.variant.sku,
                product_name=line.product.name,
                product_slug=line.product.slug,
                variant_name=line.variant.variant_name,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
                currency=line.variant.currency,
                available=line.available,
            )
            for line in lines
        ],
        item_count=sum(line.quantity for line in lines if line.available),
        subtotal=subtotal,
        shipping_fee=shipping_fee,
        grand_total=(subtotal + shipping_fee).quantize(CENT),
    )


# --------------------------------------------------------------------------
# Checkout
# --------------------------------------------------------------------------
def fingerprint(payload: CheckoutRequest) -> str:
    """Băm nội dung yêu cầu — dùng lại CÙNG khoá với nội dung KHÁC là lỗi của client."""
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


ORDER_NUMBER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_order_number() -> str:
    """`VP<yymmdd>-<6 ký tự>` — không lộ số thứ tự đơn (không đếm được doanh số)."""
    suffix = "".join(secrets.choice(ORDER_NUMBER_ALPHABET) for _ in range(6))
    return f"VP{datetime.now(UTC):%y%m%d}-{suffix}"


@dataclass(frozen=True)
class CheckoutResult:
    order: Order
    replayed: bool


def _replay_or_conflict(db: Session, existing: Order, token: str | None, fp: str) -> CheckoutResult:
    if not token_matches(token, existing.owner_token_hash):
        # Khoá của người khác: không xác nhận gì về đơn đó.
        raise ApiError(
            409, "IDEMPOTENCY_KEY_CONFLICT", "Khoá idempotency đã được dùng cho yêu cầu khác."
        )
    if existing.request_fingerprint != fp:
        raise ApiError(
            422,
            "IDEMPOTENCY_KEY_REUSED",
            "Khoá idempotency đã dùng cho một yêu cầu có nội dung khác.",
        )
    return CheckoutResult(order=existing, replayed=True)


def _order_by_key(db: Session, key: str) -> Order | None:
    return db.execute(select(Order).where(Order.idempotency_key == key)).scalar_one_or_none()


def record_status_event(
    db: Session,
    order: Order,
    *,
    field: str,
    from_value: str | None,
    to_value: str,
    actor: str,
    reason: str | None = None,
) -> None:
    db.add(
        OrderStatusEvent(
            order_id=order.id,
            field=field,
            from_value=from_value,
            to_value=to_value,
            actor=actor,
            reason=reason,
        )
    )


def checkout(
    db: Session,
    payload: CheckoutRequest,
    *,
    idempotency_key: str,
    token: str | None,
    hooks: tuple = (),
) -> CheckoutResult:
    """Tạo đơn từ giỏ. Xem docstring đầu file, luật 1-4.

    `hooks` là các hàm `(db, order, payload) -> None` chạy TRONG cùng giao dịch,
    sau khi đơn và dòng đơn đã có id (G17 thanh toán, kho giữ hàng). Hook ném lỗi
    ⇒ cả đơn rollback — không bao giờ có đơn "nửa vời".
    """
    fp = fingerprint(payload)

    existing = _order_by_key(db, idempotency_key)
    if existing is not None:
        return _replay_or_conflict(db, existing, token, fp)

    cart = get_owned_cart(db, payload.cart_id, token, lock=True)

    # Kiểm LẠI sau khi có khoá: request cùng khoá có thể vừa tạo đơn xong trong
    # lúc ta chờ khoá giỏ.
    existing = _order_by_key(db, idempotency_key)
    if existing is not None:
        return _replay_or_conflict(db, existing, token, fp)

    if cart.status != CartStatus.ACTIVE:
        prior = db.execute(select(Order).where(Order.cart_id == cart.id)).scalar_one_or_none()
        raise ApiError(
            409,
            "CART_ALREADY_CHECKED_OUT",
            "Giỏ hàng này đã được đặt thành đơn.",
            fields={"order_id": str(prior.order_id)} if prior else None,
        )

    lines = priced_lines(db, cart)
    if not lines:
        raise ApiError(422, "CART_EMPTY", "Giỏ hàng đang trống.")
    unavailable = [line.variant.sku for line in lines if not line.available]
    if unavailable:
        raise ApiError(
            409,
            "SKU_UNAVAILABLE",
            "Một số sản phẩm trong giỏ đã ngừng bán. Vui lòng bỏ ra khỏi giỏ.",
            fields={"skus": ",".join(unavailable)},
        )
    currencies = {line.variant.currency for line in lines}
    if currencies != {cart.currency}:
        raise ApiError(409, "CURRENCY_MISMATCH", "Giỏ hàng có sản phẩm khác đơn vị tiền tệ.")

    subtotal = sum((line.line_total for line in lines), ZERO).quantize(CENT)
    shipping_fee = shipping_fee_for(subtotal)
    discount_total = ZERO
    grand_total = (subtotal + shipping_fee - discount_total).quantize(CENT)

    if payload.expected_total is not None and payload.expected_total.quantize(CENT) != grand_total:
        raise ApiError(
            409,
            "PRICE_CHANGED",
            "Giá đã thay đổi. Vui lòng xem lại giỏ hàng trước khi đặt.",
            fields={"grand_total": str(grand_total)},
        )

    customer = find_or_create_customer_by_contact(
        db,
        full_name=payload.customer.full_name,
        phone=payload.customer.phone,
        email=payload.customer.email,
    )

    order = Order(
        order_id=uuid.uuid4(),
        order_number=new_order_number(),
        customer_id=customer.id,
        cart_id=cart.id,
        idempotency_key=idempotency_key,
        request_fingerprint=fp,
        owner_token_hash=cart.owner_token_hash,
        status=OrderStatus.PENDING_PAYMENT.value,
        payment_status=PaymentStatus.UNPAID.value,
        currency=cart.currency,
        subtotal=subtotal,
        shipping_fee=shipping_fee,
        discount_total=discount_total,
        grand_total=grand_total,
        customer_note=payload.customer_note,
    )
    db.add(order)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        # Cùng khoá vừa được giao dịch khác ghi (khoá giỏ không phủ trường hợp
        # khoá bị dùng cho HAI giỏ khác nhau). DB là trọng tài cuối cùng.
        db.rollback()
        existing = _order_by_key(db, idempotency_key)
        if existing is None:
            raise
        return _replay_or_conflict(db, existing, token, fp)

    for line in lines:
        db.add(
            OrderItem(
                order_id=order.id,
                sku_id=line.variant.id,
                sku=line.variant.sku,
                product_name=line.product.name,
                variant_name=line.variant.variant_name,
                unit_price=line.unit_price,
                quantity=line.quantity,
                line_total=line.line_total,
            )
        )
    db.add(
        ShippingAddress(
            order_id=order.id,
            recipient_name=payload.shipping.recipient_name,
            phone=payload.shipping.phone,
            address_line=payload.shipping.address_line,
            ward=payload.shipping.ward,
            district=payload.shipping.district,
            province=payload.shipping.province,
        )
    )
    record_status_event(
        db,
        order,
        field="status",
        from_value=None,
        to_value=order.status,
        actor="customer:checkout",
    )
    cart.status = CartStatus.CHECKED_OUT.value
    db.flush()

    for hook in hooks:
        hook(db, order, payload)

    db.commit()
    db.refresh(order)
    return CheckoutResult(order=order, replayed=False)


# --------------------------------------------------------------------------
# Đọc đơn
# --------------------------------------------------------------------------
def order_items(db: Session, order: Order) -> list[OrderItem]:
    return list(
        db.execute(
            select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id.asc())
        )
        .scalars()
        .all()
    )


def shipping_for(db: Session, order: Order) -> ShippingAddress:
    return db.execute(
        select(ShippingAddress).where(ShippingAddress.order_id == order.id)
    ).scalar_one()


def get_owned_order(db: Session, order_id: uuid.UUID, token: str | None) -> Order:
    """Đơn của CHÍNH chủ. Không có / sai token ⇒ CÙNG 404 (chống IDOR + dò)."""
    order = db.execute(select(Order).where(Order.order_id == order_id)).scalar_one_or_none()
    if order is None or not token_matches(token, order.owner_token_hash):
        raise NotFound("ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
    return order


def serialize_order(db: Session, order: Order) -> OrderOut:
    shipping = shipping_for(db, order)
    return OrderOut(
        order_id=order.order_id,
        order_number=order.order_number,
        status=order.status,
        payment_status=order.payment_status,
        currency=order.currency,
        subtotal=order.subtotal,
        shipping_fee=order.shipping_fee,
        discount_total=order.discount_total,
        grand_total=order.grand_total,
        items=[OrderItemOut.model_validate(item) for item in order_items(db, order)],
        recipient_name=shipping.recipient_name,
        phone_masked=mask_phone(shipping.phone),
        province=shipping.province,
        created_at=order.created_at,
    )


# --------------------------------------------------------------------------
# Chuyển trạng thái — ĐƯỜNG DUY NHẤT
# --------------------------------------------------------------------------
#: Hook chạy khi đơn chuyển trạng thái (ví dụ: kho nhả hàng giữ khi huỷ).
STATUS_HOOKS: list = []


def change_order_status(
    db: Session, order: Order, to_status: str, *, actor: str, reason: str | None = None
) -> Order:
    current = order.status
    if to_status not in ORDER_TRANSITIONS:
        raise ApiError(422, "UNKNOWN_STATUS", "Trạng thái đơn không hợp lệ.")
    if to_status not in ORDER_TRANSITIONS[current]:
        raise ApiError(
            409,
            "INVALID_STATUS_TRANSITION",
            f"Không thể chuyển đơn từ {current} sang {to_status}.",
        )
    for hook in STATUS_HOOKS:
        hook(db, order, current, to_status, actor)
    order.status = to_status
    record_status_event(
        db,
        order,
        field="status",
        from_value=current,
        to_value=to_status,
        actor=actor,
        reason=reason,
    )
    db.flush()
    return order


def set_payment_status(
    db: Session, order: Order, to_status: str, *, actor: str, reason: str | None = None
) -> Order:
    """Đổi `orders.payment_status`. CHỈ tầng dịch vụ thanh toán được gọi hàm này."""
    current = order.payment_status
    if to_status == current:
        return order
    if to_status not in PAYMENT_TRANSITIONS.get(current, frozenset()):
        raise ApiError(
            409,
            "INVALID_PAYMENT_TRANSITION",
            f"Không thể chuyển thanh toán từ {current} sang {to_status}.",
        )
    order.payment_status = to_status
    record_status_event(
        db,
        order,
        field="payment_status",
        from_value=current,
        to_value=to_status,
        actor=actor,
        reason=reason,
    )
    db.flush()
    return order


def count_items(db: Session, order_pks: list[int]) -> dict[int, int]:
    if not order_pks:
        return {}
    rows = db.execute(
        select(OrderItem.order_id, func.sum(OrderItem.quantity))
        .where(OrderItem.order_id.in_(order_pks))
        .group_by(OrderItem.order_id)
    ).all()
    return {order_pk: int(total) for order_pk, total in rows}


def customer_for(db: Session, order: Order) -> Customer:
    return db.execute(select(Customer).where(Customer.id == order.customer_id)).scalar_one()
