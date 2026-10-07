# G17 — Nền tảng thanh toán (độc lập nhà cung cấp)

Migration `0010_payments` (additive). **Không** có tích hợp ngân hàng/cổng thật nào — `REAL PAYMENT PROVIDER = NOT INTEGRATED`.

## 1. Giao diện nhà cung cấp — `app/payments/base.py`

| Thao tác | Ý nghĩa |
|---|---|
| `create_payment(db, order)` | tạo khoản thu cho đơn (số tiền = `orders.grand_total`) |
| `get_status(payment)` | trạng thái theo nhà cung cấp |
| `verify_webhook(headers, body)` | chữ ký + thời gian — **không đụng DB** |
| `handle_webhook(db, headers, body)` | xử lý webhook đã verify |

Thêm cổng thật sau này = thêm một lớp; tầng dịch vụ/đơn hàng không đổi.

## 2. Phương thức

| Phương thức | Khởi đầu | Thành `PAID` khi |
|---|---|---|
| `COD` | `PENDING` | **chỉ** nhân viên xác nhận đã thu, **và** đơn đã `SHIPPED`/`COMPLETED`. Không bao giờ tự động. |
| `BANK_TRANSFER_MANUAL` | `PENDING` | nhân viên đối soát sao kê rồi xác nhận. Khách ghi nội dung CK = mã đơn. |
| `STAGING_MOCK` | `PENDING` | webhook **đã ký**. Nhân viên không xác nhận tay được. **Tắt ở production** dù có khoá. |

Phương thức dùng được công bố ở `GET /api/public-config` → `payment_methods`.

## 3. Trạng thái

Khoản thu: `CREATED/PENDING → PAID | FAILED | CANCELLED`, `PAID → REFUNDED`; `FAILED/CANCELLED/REFUNDED` là cuối.

Đồng bộ `orders.payment_status` (chỉ qua `services.payments.transition()` → `commerce.set_payment_status()`):

| payments.status | orders.payment_status |
|---|---|
| CREATED | UNPAID |
| PENDING | PENDING |
| PAID | PAID |
| FAILED | FAILED |
| CANCELLED | UNPAID |
| REFUNDED | REFUNDED |

Huỷ đơn ⇒ khoản thu đang chờ thành `CANCELLED`. Khoản đã `PAID` **giữ nguyên** tới khi nhân viên ghi nhận hoàn tiền
(`refund`, chỉ cho đơn đã huỷ). Partial unique index: **tối đa một** khoản thu mở/đã trả mỗi đơn.

## 4. Webhook giả lập — `POST /api/payments/webhooks/staging-mock`

- Header `X-Mock-Timestamp` (giây Unix) + `X-Mock-Signature` = `hex(HMAC-SHA256(PAYMENT_MOCK_WEBHOOK_SECRET, "<ts>.<body>"))`.
- Lệch thời gian > `PAYMENT_WEBHOOK_TOLERANCE_SECONDS` (mặc định 300) ⇒ 401.
- Chữ ký/thời gian sai ⇒ **401, không ghi gì vào DB**.
- Body: `{event_id, payment_reference, status: PAID|FAILED, amount, currency}`.

| Kiểm | Sai ⇒ |
|---|---|
| chống trùng `(provider, event_id)` UNIQUE | 200 `DUPLICATE`, không đổi gì |
| khoản thu theo `payment_reference` (khớp đơn/khoản thu) | 404 `PAYMENT_NOT_FOUND` |
| trạng thái báo về hợp lệ | 422 `UNKNOWN_STATUS` |
| `amount` == `payments.amount` (Decimal, không làm tròn) | 422 `AMOUNT_MISMATCH` |
| `currency` == `payments.currency` | 422 `CURRENCY_MISMATCH` |
| chuyển trạng thái hợp lệ | 409 `INVALID_TRANSITION` |

Mọi lối ra sau khi verify ghi **đúng một** `payment_events` (APPLIED/REJECTED). Không lưu payload thô, chữ ký hay
dữ liệu tài khoản — chỉ trường đã kiểm + `payload_sha256`.

## 5. Quản trị (`require_staff`)

`GET /api/admin/payments` (lọc `status`, `method`) · `GET /api/admin/orders/{order_id}/payments` (kèm vết) ·
`POST /api/admin/payments/{payment_id}/confirm|fail|refund` `{note}`.

## 6. Tracking (không PII, không dữ liệu thanh toán nhạy cảm)

| Event | Trường |
|---|---|
| `vipphone_payment_method_selected` | `payment_method` |
| `vipphone_payment_pending` / `_succeeded` / `_failed` | `order_number`, `payment_method`, `value`, `currency` |

## 7. Cấu hình

| Biến | Mặc định | Ghi chú |
|---|---|---|
| `PAYMENT_MOCK_WEBHOOK_SECRET` | rỗng (tắt) | chỉ staging/dev; **không** đặt ở production |
| `PAYMENT_WEBHOOK_TOLERANCE_SECONDS` | 300 | |
| `BANK_TRANSFER_INSTRUCTIONS` | rỗng | số TK/ngân hàng hiển thị cho khách — Owner cung cấp |
