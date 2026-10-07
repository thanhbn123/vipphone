# G15 — Engine gợi ý phụ kiện (V1)

Issue: [#63](https://github.com/thanhbn123/vipphone/issues/63). Engine **theo luật, xác định** — không AI/ML.

## 1. Đầu vào / đầu ra

`GET /api/recommendations?device_model=<mã máy>&limit=<1..24, mặc định 8>`

- Đầu vào DUY NHẤT là **mã máy** (`iphone_models.model_code`). Không có tham số nào về khách
  ⇒ đường công khai này không thể lộ PII.
- Mã máy không có trong danh mục **đang hoạt động** ⇒ **422 `MODEL_NOT_IN_CATALOG`** (không trả
  200-rỗng: rỗng trông y như "chưa có phụ kiện" và che lỗi phía gọi).
- Đầu ra: `{context, device_model_code, items: [{rank, category_code, product}]}`. `product` là
  **chính** `ProductOut` công khai của G14 ⇒ không có `cost_price`.

## 2. Luật

| # | Luật | Cài ở đâu |
|---|---|---|
| 1 | Chỉ hàng tương thích **đúng** máy | `catalog.product_query(ProductFilters(device_model=…, active_only=True))` — **cùng** đường lọc của G14, không viết đường thứ hai |
| 2 | Product `active` **và** SKU `active` | như trên (`active_only=True` + `EXISTS` trên SKU active) |
| 3 | Category `active` | `Category.active IS TRUE` trong truy vấn gợi ý |
| 4 | Thứ tự nhóm hàng là **dữ liệu** | bảng `recommendation_category_priority` (migration `0008`) |
| 5 | Sau quà ốp **không** gợi ý ốp | `CASE` không có dòng nào trong context `POST_GIFT` ⇒ không khớp JOIN |
| 6 | Chỉ trả SKU tương thích đúng máy | lọc `variants` theo `compatibility.device_model_code` |
| 7 | Loại hàng đã mua | điểm mở rộng `exclude_product_ids` (khoá nội bộ, không nhận từ trình duyệt) — G16 nối vào |

## 3. Thứ tự — xác định toàn phần

`ORDER BY priority ASC, products.name ASC, products.id ASC`

`products.id` là khoá phá hoà cuối và là duy nhất ⇒ cùng đầu vào luôn ra cùng thứ tự.
UNIQUE `(context, priority)` ở tầng DB: hai nhóm cùng hạng sẽ làm thứ tự phụ thuộc thứ tự đọc
đĩa của PostgreSQL — chặn ở DB.

Thứ tự đã duyệt cho `POST_GIFT`:
`SCREEN_PROTECTOR → CHARGER → CABLE → MAGSAFE → POWER_BANK → EARPHONE → CAR_ACCESSORY`.

Đổi thứ tự = `UPDATE recommendation_category_priority …` — không cần deploy. Bảng **chưa có
route admin** (cùng chính sách với `categories`, xem `docs/catalog.md` §2.1).

## 4. Giao diện

`/success.html`: khung gợi ý **mềm**, ẩn tới khi có dữ liệu; lỗi API thì im lặng không hiện
(gợi ý là phần phụ, không được làm hỏng trang mã quà). Ba CTA:
"Xem kính phù hợp" · "Xem sạc/cáp phù hợp" · "Xem phụ kiện cho máy của bạn" → `/shop?category=…&device_model=…`.
Không popup, không ép mua. Vẽ bằng DOM + `textContent`.

Mã máy được `app.js` lưu vào `sessionStorage` (`model_code`) lúc gửi form — không phải PII.

## 5. Tracking (dataLayer, KHÔNG PII)

| Event | Trường |
|---|---|
| `vipphone_recommendation_view` | `device_model_code`, `source_surface`, `item_count`, `product_ids` |
| `vipphone_recommendation_click` | `product_id`, `sku`, `category`, `device_model_code`, `source_surface`, `rank` |
| `vipphone_product_view` | `product_id`, `sku`, `category`, `source_surface` |

**Cấm**: `phone`, `email`, `full_name`, `address`. Có test E2E kiểm theo **khoá** và theo
**giá trị** thật của khách.

## 6. Ngoài phạm vi V1

Gợi ý theo khách cụ thể (phải qua `require_staff`), cá nhân hoá theo lịch sử mua (cần G16),
route admin cho bảng ưu tiên.
