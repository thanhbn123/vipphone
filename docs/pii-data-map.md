# Bản đồ dữ liệu PII — VIP PHONE

> Câu hỏi tài liệu này trả lời: **dữ liệu nào đang được thu, nằm ở đâu, ai đọc được, dùng làm gì.**
>
> Câu hỏi tài liệu này **KHÔNG** trả lời: *giữ bao lâu*. Đó là **quyết định của Owner** —
> xem [`decisions/PII_RETENTION_OPTIONS.md`](decisions/PII_RETENTION_OPTIONS.md).
>
> Đo trên `develop` = `f79834fcd36778994a62248747ff3cc114d4e88b`.

---

## 1. Phân loại

| Nhãn | Nghĩa |
|---|---|
| **DIRECT ID** | Nhận diện trực tiếp một người. Mất/ lộ là ảnh hưởng tới chính người đó |
| **BUSINESS META** | Thông tin công việc; có thể gián tiếp chỉ ra người nhưng không định danh một mình |
| **MARKETING ATTR** | Quy kết nguồn; **không** chứa PII nếu đúng quy ước (xem §5) |
| **AUDIT** | Vết thao tác; phục vụ truy vết, không phục vụ tiếp thị |
| **KEY** | Định danh kỹ thuật, không phải PII |

---

## 2. Bảng dữ liệu chính — bảng `leads`

| Trường | Loại | Vì sao thu | Bắt buộc | Nơi lưu | Ai đọc được | Dùng làm gì |
|---|---|---|---|---|---|---|
| `full_name` | **DIRECT ID** | Gọi tên khách khi phát quà | **Có** | `leads.full_name` | Nhân viên (tra cứu + admin), CSV export | Xác nhận danh tính tại quầy |
| `phone` | **DIRECT ID** | Liên hệ xác nhận quà; **khoá chống trùng** | **Có** | `leads.phone` (đã chuẩn hoá `0xxxxxxxxx`) | Nhân viên **chỉ thấy dạng che** `0912***678`; **admin thấy đủ**; CSV export đủ | Liên hệ + chống cấp trùng |
| `company_name` | **BUSINESS META** | Bối cảnh BNI/doanh nghiệp | Không | `leads.company_name` | Admin, CSV | Phân khúc B2B |
| `bni_chapter` | **BUSINESS META** | Thuộc chapter nào | Không | `leads.bni_chapter` | Admin, CSV | Đo hiệu quả theo chapter |
| `referrer_name` | **DIRECT ID** | Ghi công người giới thiệu | Không | `leads.referrer_name` | Admin, CSV | Ghi công giới thiệu |
| `iphone_model` | **BUSINESS META** | Chọn đúng ốp | **Có** | `leads.iphone_model` | Nhân viên, admin, CSV | Chuẩn bị quà đúng máy |
| `iphone_year` | BUSINESS META | Từ danh mục, **không** lấy từ client | **Có** | `leads.iphone_year` | Nhân viên, admin, CSV | — |
| `case_color` | **BUSINESS META** | Sở thích màu | **Có** | `leads.case_color` | Nhân viên, admin, CSV | Chuẩn bị quà |
| `consent` | **AUDIT** | Bằng chứng khách đồng ý | **Có** (phải `true`) | `leads.consent` | Admin, CSV | Chứng minh có cơ sở xử lý |
| `source` | **MARKETING ATTR** | Nguồn khách chọn | Không | `leads.source` | Admin, CSV | Kênh nào hiệu quả |
| `campaign` | **MARKETING ATTR** | Chiến dịch | Không | `leads.campaign` | Admin, CSV | — |
| `utm_source` | **MARKETING ATTR** | UTM | Không | `leads.utm_source` | Admin, CSV | Quy kết |
| `utm_medium` | **MARKETING ATTR** | UTM | Không | `leads.utm_medium` | Admin, CSV | Quy kết |
| `utm_campaign` | **MARKETING ATTR** | UTM | Không | `leads.utm_campaign` | Admin, CSV | Quy kết |
| `utm_content` | **MARKETING ATTR** | UTM | Không | `leads.utm_content` | Admin, CSV | Quy kết |
| `ref` | **MARKETING ATTR** | Mã thành viên giới thiệu | Không | `leads.ref` | Admin, CSV | Ghi công |
| `lead_id` | **KEY** | Định danh công khai | Có | `leads.lead_id` (UUID) | Nhân viên, admin, CSV | Tham chiếu |
| `gift_code` | **KEY** | Khách dùng để nhận quà | Có | `leads.gift_code` | **Công khai** (in trên QR/phiếu) | Tra cứu + phát quà |
| `gift_status` | **AUDIT** | Trạng thái phát quà | Có | `leads.gift_status` | Nhân viên, admin, CSV | Vòng đời quà |
| `created_at` / `updated_at` | **AUDIT** | Mốc thời gian | Có | `leads.*` | Admin, CSV | Đối soát |
| `redeemed_at` | **AUDIT** | Lúc phát quà | Không | `leads.redeemed_at` | Nhân viên, admin | Chống phát lại |
| `redeemed_by` | **AUDIT** | **Ai** phát quà | Không | `leads.redeemed_by` = `staff:<12 hex SHA-256 của khoá>` | Nhân viên, admin | Truy vết |
| `id` | KEY nội bộ | Khoá kỹ thuật | Có | `leads.id` | Không lộ ra API | — |

### 2.1 Bảng `audit_events`

| Trường | Loại | Ghi chú |
|---|---|---|
| `event_id`, `event_type`, `created_at` | AUDIT | — |
| `lead_id`, `gift_code`, `lead_pk` | KEY | Tham chiếu, không phải PII |
| `actor` | AUDIT | Khách: `public:<ip>` · Nhân viên: `staff:<12 hex>` |
| `metadata` (JSONB) | AUDIT | **Đi qua DANH SÁCH TRẮNG khoá**; khoá lạ bị loại **và ghi log**. Có danh sách đen riêng cho `phone`, `full_name`, `company_name`, `token`, `secret` |

**IP của khách nằm trong `actor`.** IP là dữ liệu cá nhân theo nghĩa rộng — cần nằm trong quyết
định retention, không được bỏ quên.

### 2.2 Bảng `iphone_models`

Danh mục sản phẩm. **Không chứa PII.**

---

## 3. Ai đọc được gì — ranh giới thật

| Bề mặt | Xác thực | Thấy gì |
|---|---|---|
| `POST /api/leads` | công khai (+rate limit) | chỉ **ghi**, không đọc |
| `GET /api/gifts/{code}/qr.png` | công khai | **ảnh QR** — chỉ chứa URL công khai, **có test chứng minh không chứa PII** |
| `GET /api/gifts/{code}` | **nhân viên** | `full_name`, `phone_masked`, model/năm/màu, status. **KHÔNG** có UTM/công ty/BNI/người giới thiệu |
| `GET /api/admin/leads` (+CSV, chi tiết) | **nhân viên** | **đủ trường** — ranh giới nằm ở **xác thực**, không nằm ở che bớt |
| `GET /api/health` | công khai | không có dữ liệu |
| `GET /api/ready` | công khai | **chỉ `status`**. Chi tiết (migration head, cấu hình) chỉ khi có khoá nhân viên |
| `/admin-leads.html` | công khai (trang tĩnh) | **chỉ là cái vỏ rỗng** — mọi dữ liệu nằm sau `/api/admin/*`, đều bắt buộc khoá |

**Chưa cấu hình `STAFF_API_KEYS` ⇒ tất cả bề mặt nhân viên trả 503** (fail closed).

---

## 4. Dữ liệu rời khỏi hệ thống

| Đường ra | Chứa PII? | Kiểm soát |
|---|---|---|
| **CSV export** | **Có — đủ trường** | Chỉ nhân viên; chống formula injection; có BOM UTF-8; có trần số dòng và header báo khi bị cắt |
| **QR** | **Không** | Có test giải mã QR thật khẳng định không có tên/SĐT/công ty |
| **`window.dataLayer`** (trình duyệt khách) | **Không** | Chỉ event + model + `gift_code`; **không** đẩy tên/SĐT |
| **`sessionStorage`** (máy khách) | **Có, giới hạn** | Trang thành công giữ `full_name`/model/màu để hiển thị lại; **cố ý KHÔNG lưu SĐT** |
| **Log máy chủ** | **IP** | `security.py` ghi IP khi xác thực nhân viên thất bại. **Chưa rà soát** PII khác lọt log |
| **CRM / GTM / GA4** | **Chưa nối** | `TRACKING = DATA_LAYER_ONLY` — chưa có đường ra nào đang hoạt động |

---

## 5. Quy ước bảo vệ PII (đang có hiệu lực)

1. **Không PII trong QR.** Có test giải mã ảnh thật.
2. **Không PII trong query string.** Frontend chỉ đọc **whitelist 7 tham số**; server kiểm lại bằng
   `^[A-Za-z0-9._~-]{1,64}$`. Giá trị có khoảng trắng/dấu `<`/dấu nháy bị **422**.
3. **Không PII dư thừa trong audit.** Metadata qua danh sách trắng khoá.
4. **Che bớt tại quầy.** Nhân viên chỉ thấy `0912***678`.
5. **Không PII trong `error` trả về.** Body lỗi không dội lại giá trị đã gửi (có test).
6. **Khoá nhân viên không vào `localStorage`** — chỉ `sessionStorage`, có chốt chặn trong CI.

---

## 6. Ba khoảng trống đã biết — ghi thẳng

| # | Khoảng trống | Ảnh hưởng |
|---|---|---|
| G1 | **Retention chưa quyết.** Dữ liệu hiện **giữ vô thời hạn** | Càng để lâu càng khó xoá đúng. Cần Owner chọn phương án |
| G2 | **Chưa có cơ chế xoá/ẩn danh theo yêu cầu** (quyền được xoá) | Hiện phải xoá tay bằng SQL. **Chưa có API, chưa có quy trình** |
| G3 | **Chưa rà soát PII lọt vào log** production | Nghi ngờ thấp (không thấy chỗ nào log tên/SĐT) nhưng **chưa đo** |

**Cách xoá tay (khi được yêu cầu, ở staging):**

```sql
-- Xoá một lead theo gift_code (audit giữ lại nhưng lead_pk thành NULL)
DELETE FROM leads WHERE gift_code = 'VIP-26-XXXXXX';
```

`audit_events.lead_pk` có `ON DELETE SET NULL`, còn `lead_id`/`gift_code` trong audit **vẫn nằm lại**.
Đó là chủ ý (giữ vết kiểm toán) nhưng **cũng là PII còn sót** — phải nằm trong quyết định retention.
