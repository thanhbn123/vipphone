# G16 — Giỏ hàng + đơn hàng

Issue: [#67](https://github.com/thanhbn123/vipphone/issues/67). Migration `0009_cart_order` (additive).

## 1. Bảng

| Bảng | Vai trò | Ràng buộc chính |
|---|---|---|
| `carts` | giỏ; `owner_token_hash` = SHA-256 token sở hữu | `cart_id` UNIQUE, status ∈ ACTIVE/CHECKED_OUT/ABANDONED |
| `cart_items` | dòng giỏ (SKU + số lượng) — **không có cột giá** | UNIQUE (cart, sku), 1 ≤ qty ≤ 99 |
| `orders` | đơn | UNIQUE `order_id`, `order_number`, **`idempotency_key`**, **`cart_id`**; CHECK status/payment_status; CHECK `grand_total = subtotal + shipping_fee - discount_total` |
| `order_items` | **ảnh chụp** tên + giá lúc đặt | CHECK `line_total = unit_price * quantity`; FK SKU `RESTRICT` |
| `shipping_addresses` | địa chỉ giao (1/đơn) | CHECK SĐT chuẩn hoá |
| `order_status_events` | vết mọi lần đổi `status`/`payment_status` | actor + lý do, không PII |

Tiền: `Numeric(12,2)` / `Decimal` ở mọi tầng.

## 2. API

Công khai — quyền là **token sở hữu**, không phải khoá nhân viên. Sai/thiếu token ⇒ **404** giống hệt "không tồn tại".

| Route | Header | Ghi chú |
|---|---|---|
| `POST /api/cart` | — | trả `cart_token` **một lần**; rate limit riêng |
| `GET /api/cart/{cart_id}` | `X-Cart-Token` | giá hiện hành, `available`, `subtotal`, `shipping_fee`, `grand_total` |
| `POST /api/cart/{cart_id}/items` | `X-Cart-Token` | `{sku, quantity}` — chỉ SKU active + product active |
| `PATCH /api/cart/{cart_id}/items/{sku}` | `X-Cart-Token` | `{quantity}` |
| `DELETE /api/cart/{cart_id}/items/{sku}` | `X-Cart-Token` | |
| `POST /api/checkout` | `X-Cart-Token`, **`Idempotency-Key`** | tạo đơn |
| `GET /api/orders/{order_id}` | `X-Order-Token` (= token giỏ) | chủ đơn xem đơn, SĐT đã che |

Quản trị (`require_staff`): `GET /api/admin/orders` (lọc `status`, `payment_status`, `q` = mã đơn / SĐT),
`GET /api/admin/orders/{order_id}`, `POST /api/admin/orders/{order_id}/status`.

Không cookie ⇒ không có bề mặt CSRF (trình duyệt khác origin không tự gửi header token; CORS chỉ mở origin đã khai).

## 3. Máy chủ giữ giá

- Không trường nào nhận giá/tổng để **tính**. Body có `unit_price`/`grand_total`/`items` ⇒ 422 (`extra="forbid"`).
- `expected_total` (không bắt buộc) = tổng khách **đã thấy**. Lệch tổng máy chủ tính ⇒ **409 `PRICE_CHANGED`**, không tạo đơn.
- Phí ship: **một** hàm `shipping_fee_for()` cho cả giỏ và checkout; mặc định `SHIPPING_FEE_FLAT=0.00`
  vì chưa có biểu phí được duyệt (Owner decision).

## 4. Idempotency + đồng thời

1. Có đơn với cùng `Idempotency-Key` ⇒ trả lại đơn đó (`replayed=true`) nếu cùng chủ + cùng nội dung;
   khác nội dung ⇒ 422 `IDEMPOTENCY_KEY_REUSED`; khoá của người khác ⇒ 409 (không lộ đơn).
2. Khoá giỏ `SELECT … FOR UPDATE` ⇒ checkout của cùng giỏ xếp hàng.
3. Sau khi có khoá: kiểm lại khoá idempotency; giỏ đã `CHECKED_OUT` ⇒ 409 `CART_ALREADY_CHECKED_OUT` (kèm `order_id` cho chính chủ).
4. DB là trọng tài cuối: UNIQUE `idempotency_key` + UNIQUE `cart_id`.

Test: 8 luồng đồng thời, cùng khoá và khác khoá ⇒ **đúng 1 đơn, 1 dòng đơn**.

## 5. Trạng thái

```
DRAFT → PENDING_PAYMENT → CONFIRMED → PROCESSING → SHIPPED → COMPLETED
   └──────────┴──────────────┴────────────┴→ CANCELLED     (COMPLETED, CANCELLED là trạng thái cuối)
```

Thanh toán: `UNPAID → PENDING → PAID → REFUNDED`, `PENDING → FAILED → PENDING`. `payment_status` **chỉ** đổi qua
`commerce.set_payment_status()` (gọi bởi tầng thanh toán G17). Mọi lần đổi ghi `order_status_events`.

Checkout tạo đơn ở `PENDING_PAYMENT` / `UNPAID`.

## 6. Giao diện + tracking

`/product/{slug}` (nút THÊM VÀO GIỎ) → `/cart` → `/checkout` → `/order/success`. Trình duyệt chỉ giữ `cart_id` +
`cart_token` (localStorage). `Idempotency-Key` sinh **một lần mỗi giỏ** (sessionStorage) ⇒ bấm đúp/tải lại không tạo đơn thứ hai.

| Event | Trường (không PII) |
|---|---|
| `vipphone_add_to_cart` | `product_id`, `sku`, `category`, `quantity`, `source_surface` |
| `vipphone_remove_from_cart` | `sku`, `quantity` |
| `vipphone_checkout_start` | `value`, `currency`, `item_count` |
| `vipphone_order_created` | `order_number`, `value`, `currency`, `item_count` |

## 7. Ngoài phạm vi G16

Thanh toán (G17), giữ hàng/tồn kho (gate kho), biểu phí ship thật, mã giảm giá (`discount_total` luôn 0).
