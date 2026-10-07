# Kho tối giản (inventory foundation)

Migration `0011_inventory` (additive). **Một kho** — không đa kho (nghiệp vụ hiện tại không cần).

## 1. Khái niệm

| Bảng | Nội dung |
|---|---|
| `inventory_balances` | mỗi SKU một dòng: `quantity_on_hand`, `quantity_reserved`, `quantity_available` (**cột sinh** = on_hand − reserved) |
| `inventory_movements` | **sổ cái chỉ-thêm**: `movement_type`, `delta_on_hand`, `delta_reserved`, `order_id?`, `actor`, `reason` |

Bất biến ở DB: `on_hand ≥ 0`, `reserved ≥ 0`, `reserved ≤ on_hand`. Số dư = tổng sổ cái (có test đối chiếu).

## 2. Loại biến động

| Loại | Ai ghi | delta_on_hand | delta_reserved |
|---|---|---|---|
| `OPENING` | nhân viên, **một lần** khi SKU chưa có sổ | +q | 0 |
| `RECEIPT` | nhân viên (nhập hàng) | +q | 0 |
| `ADJUSTMENT` | nhân viên, **bắt buộc lý do** (kiểm kê) | ±q | 0 |
| `RETURN` | nhân viên, **bắt buộc lý do** (khách trả) | +q | 0 |
| `RESERVE` | checkout | 0 | +q |
| `RELEASE` | đơn bị huỷ | 0 | −q |
| `SALE` | đơn chuyển `SHIPPED` | −q | −q |

`RESERVE/RELEASE/SALE` **không** ghi tay được (422).

## 3. Phạm vi theo dõi

Chỉ SKU có `product_variants.stock_tracking = true`. SKU không theo dõi bán như G14 (không giới hạn).
SKU có theo dõi mà chưa có sổ ⇒ **hết hàng** (không đoán là còn).

## 4. Không bán vượt

Checkout (hook chạy trước tạo khoản thu): khoá `inventory_balances … FOR UPDATE` theo **thứ tự `sku_id` tăng dần**
(chống deadlock giữa đơn nhiều SKU), kiểm `available ≥ q`, ghi `RESERVE`. Thiếu bất kỳ SKU nào ⇒ **409 `OUT_OF_STOCK`**,
**cả đơn** rollback (không đơn, không khoản thu, không giữ hàng).

Test: 10 checkout đồng thời, tồn 3 ⇒ đúng 3 đơn, 7 `OUT_OF_STOCK`, số dư (3, 3, 0).

## 5. Công khai

`/api/products*` chỉ có nhãn `IN_STOCK`/`OUT_OF_STOCK` (SKU theo dõi còn `available > 0`). **Không** có con số tồn.

## 6. Quản trị (`require_staff`)

`GET /api/admin/inventory` (`tracked_only`, `low_stock_below`) · `GET /api/admin/inventory/{sku}` (số dư + sổ cái, kèm mã đơn) ·
`POST /api/admin/inventory/{sku}/movements` `{movement_type, quantity, reason}` — mọi dòng ghi `actor` = nhãn khoá nhân viên.

## 7. Ngoài phạm vi

Đa kho, chuyển kho, lô/hạn dùng, đồng bộ kênh ngoài, đặt trước/back-order.
