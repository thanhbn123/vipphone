# Attribution (nguồn khách / nguồn đơn)

Migration `0014_order_attribution` (additive, chỉ thêm cột nullable + backfill an toàn).

## 1. Thu thập

`assets/js/tracking.js` đọc whitelist `src, ref, campaign, utm_source, utm_medium, utm_campaign, utm_content`
(chỉ ký tự `[A-Za-z0-9._~-]`, ≤ 64) vào `sessionStorage`. Server **làm sạch lại** (`TrackingValue`, `_clean_tracking`).

| Điểm | Gửi |
|---|---|
| Form lead (`POST /api/leads`) | `source`(=src), `campaign`, `ref`, `utm_*` → cột của `leads` |
| Checkout (`POST /api/checkout`) | `attribution: {source, campaign, ref, utm_*}` → cột của `orders` |

## 2. Hai mô hình — không trộn

| Mô hình | Lưu ở | Quy tắc |
|---|---|---|
| **First-touch** của khách | `customer_acquisition` (1 dòng/khách) | ghi **một lần**: từ lead đầu tiên (`acquired_via=LEAD`), hoặc — khách đến thẳng cửa hàng — từ đơn đầu tiên (`acquired_via=ORDER`, `first_order_id`). **Không bao giờ ghi đè.** |
| **Nguồn của đơn** (last-touch lúc đặt) | `orders.source/campaign/ref/utm_*` | chụp lúc checkout, không đổi về sau |

Chuỗi liên kết: `lead → customer (customer_acquisition) → order (orders.customer_id + nguồn của đơn)`.

## 3. Báo cáo — `GET /api/admin/reports/attribution` (`require_staff`)

Tham số: `model=order|first_touch`, `dimension=source|campaign|ref|utm_source|utm_medium|utm_campaign|utm_content`,
`date_from`, `date_to` (ngày giờ VN). Trả **chỉ số tổng hợp**: `key, customers, orders, revenue, paid_revenue` — không PII.

| Câu hỏi | Gọi |
|---|---|
| nguồn nào **tạo ra khách** | `model=first_touch&dimension=source` |
| chiến dịch nào **ra đơn** | `model=order&dimension=utm_campaign` |
| referrer nào **ra doanh thu** | `model=order&dimension=ref` |

Đơn `CANCELLED` không tính đơn/doanh thu; `paid_revenue` chỉ đơn `payment_status=PAID`. `key = null` = truy cập trực tiếp.

Chi tiết đơn admin có cả `attribution` (của đơn) và `customer_first_touch`.

## 4. Ngoài phạm vi

Dashboard BI, mô hình phân bổ đa chạm (linear/time-decay), đẩy sự kiện sang GA4/Meta CAPI.
