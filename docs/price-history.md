# Lịch sử giá

Migration `0012_price_history` (additive).

## Cơ chế

- Bảng `price_history(sku_id, old_price, new_price, currency, changed_by, changed_at, reason)`.
- **Trigger PostgreSQL** `trg_product_variants_price_history` (`AFTER INSERT OR UPDATE OF sale_price`) ghi một dòng
  mỗi lần giá **thật sự đổi** (`IS DISTINCT FROM`). Vì nằm trong **cùng giao dịch** với lần đổi giá:
  - đổi giá thành công ⇒ đúng **một** dòng;
  - đổi giá thất bại / rollback ⇒ **không** dòng nào;
  - đổi bằng SQL tay cũng có vết (`changed_by = db:<role>`).
- Người sửa + lý do: ứng dụng đặt `set_config('vipphone.actor', …, true)` và `set_config('vipphone.price_reason', …, true)`
  (phạm vi **giao dịch** — không rò sang request khác dùng chung kết nối).
- Tạo SKU ⇒ dòng `old_price = NULL` (giá khởi điểm). SKU có sẵn lúc migrate ⇒ một dòng `changed_by = migration:0012`.

## API

- `PATCH /api/admin/variants/{sku}` nhận thêm `price_change_reason` (không bắt buộc).
- `GET /api/admin/variants/{sku}/price-history` (`require_staff`). Không có đường công khai.

## Đơn cũ

`order_items.unit_price` là **ảnh chụp** lúc đặt (G16) — đổi giá không đụng tới đơn đã có (có test).
