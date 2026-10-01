# Lead Schema

Nguồn chân lý triển khai là **migration Alembic** (`migrations/`). Tài liệu này mô tả hợp
đồng dữ liệu; khi lệch nhau, tin migration và `docs/MASTER_STATUS.md`.

## Bảng `leads`

| Field | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint / identity | no | khoá kỹ thuật nội bộ, **không** lộ ra ngoài |
| `lead_id` | uuid | no | **unique** — định danh công khai của lead |
| `gift_code` | text | no | **unique** — mã quà công khai |
| `full_name` | text | no | tối đa 80 ký tự |
| `phone` | text | no | **đã chuẩn hoá** dạng canonical `0xxxxxxxxx` |
| `iphone_model` | text | no | |
| `iphone_year` | integer | no | |
| `case_color` | text | no | |
| `company_name` | text | yes | tối đa 120 ký tự |
| `bni_chapter` | text | yes | tối đa 80 ký tự |
| `referrer_name` | text | yes | tối đa 80 ký tự |
| `source` | text | yes | whitelist ở tầng API |
| `campaign` | text | yes | |
| `utm_source` | text | yes | |
| `utm_medium` | text | yes | |
| `utm_campaign` | text | yes | |
| `utm_content` | text | yes | |
| `ref` | text | yes | mã thành viên giới thiệu |
| `consent` | boolean | no | phải là `true` mới nhận |
| `gift_status` | text + CHECK | no | `NEW` / `CONFIRMED` / `READY` / `REDEEMED` / `CANCELLED` |
| `created_at` | timestamptz | no | UTC, mặc định `now()` |
| `updated_at` | timestamptz | no | tự cập nhật khi `UPDATE` |
| `redeemed_at` | timestamptz | yes | chỉ set **một lần** |
| `redeemed_by` | text | yes | định danh nhân viên |

### Index bắt buộc

| Index | Cột | Mục đích |
|---|---|---|
| `uq_leads_lead_id` | `lead_id` UNIQUE | tra cứu theo định danh công khai |
| `uq_leads_gift_code` | `gift_code` UNIQUE | ràng buộc duy nhất ở tầng DB |
| `ix_leads_phone` | `phone` | kiểm tra trùng |
| `ix_leads_created_at` | `created_at` | phân trang admin |
| `ix_leads_gift_status` | `gift_status` | lọc admin |
| `ix_leads_dup` | `(phone, iphone_model, gift_status)` | chính sách chống trùng |

## Bảng `audit_events`

| Field | Type | Notes |
|---|---|---|
| `event_id` | uuid | unique |
| `event_type` | text | `LEAD_CREATED` / `GIFT_CREATED` / `GIFT_STATUS_CHANGED` / `GIFT_REDEEMED` |
| `lead_id` | uuid, null | |
| `gift_code` | text, null | |
| `actor` | text | ai/cái gì gây ra sự kiện |
| `metadata` | jsonb | **cấm chứa PII dư thừa** và **cấm chứa secret** |
| `created_at` | timestamptz | UTC |

## Bảng `iphone_models`

| Field | Type | Notes |
|---|---|---|
| `year` | integer | |
| `model_code` | text | khoá ổn định, **unique** cùng `year` |
| `display_name` | text | tên hiển thị |
| `active` | boolean | ẩn/hiện không cần sửa HTML landing |
| `sort_order` | integer | |

## Ghi chú hợp đồng

### Chuẩn hoá số điện thoại

Đầu vào được chuẩn hoá **trước khi** lưu và **trước khi** so trùng:

```
"+84 912 345 678"  →  "0912345678"
"84912345678"      →  "0912345678"
"0912.345.678"     →  "0912345678"
```

Hợp lệ với di động Việt Nam: `^0[35789]\d{8}$` (10 chữ số).

**Vì sao bắt buộc:** chính sách chống trùng dựa trên số đã chuẩn hoá. Nếu `+849…` và `09…`
cho ra hai giá trị khác nhau thì **cùng một khách sẽ nhận hai gift code**.

### Gift code

- Định dạng: `VIP-YY-XXXXXX`
- `YY` suy từ **cấu hình**, không hard-code (xem `GIFT_CODE_YEAR_PREFIX`).
- `XXXXXX`: 6 ký tự, alphabet 32 ký tự `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (bỏ `I`, `O`, `0`, `1`).
- Sinh bằng CSPRNG có đủ entropy — **không** tuần tự, **không** suy ra từ `id`.
- Tra cứu **không phân biệt** hoa/thường.
- Ràng buộc `UNIQUE` ở DB; khi đụng độ thì **thử lại**, không báo lỗi cho khách.

### Consent

`consent` phải là `true`. Bản ghi `false` bị từ chối ở tầng API, không lưu.
