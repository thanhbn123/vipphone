# ADR-0002 — Danh tính khách hàng (Customer Identity)

- **Trạng thái:** ĐỀ XUẤT — chờ Owner duyệt trước khi code
- **Gate:** G13 — Customer Foundation
- **Ngày:** 2026-10-02
- **Bối cảnh:** `develop` = `e444c96a` · migration head `0005_single_address`

---

## 1. Vấn đề

Hiện `leads` vừa là **hồ sơ khách** vừa là **vết tiếp thị**. Một khách nhận quà 3 lần
= 3 dòng `leads`, không có gì nối chúng lại. Không thể trả lời:

- Khách này đã nhận mấy món quà?
- Khách đang dùng máy nào?
- Khách đến từ đâu?
- Khách đã mua gì? (G16)

G13 tách **CUSTOMER** (danh tính thương mại lâu dài) khỏi **LEAD** (vết lịch sử).

## 2. Quyết định

### 2.1 Danh tính — SĐT chuẩn hoá, UNIQUE ở tầng DB

```
customers.phone_normalized  UNIQUE
```

**Vì sao UNIQUE thật ở DB, không chỉ kiểm ở ứng dụng:** đúng bài học đã trả giá ở
chính sách chống trùng gift — ràng buộc chỉ ở tầng ứng dụng thì **hai request đồng thời
vẫn lọt**. Hai request cùng SĐT chạy song song đều `SELECT` thấy "chưa có" rồi cùng
`INSERT` → 2 customer. UNIQUE ở DB biến cuộc đua thành một lỗi bắt được, và service
xử lý bằng `ON CONFLICT` / retry-đọc.

Chuẩn hoá dùng **đúng hàm đang dùng cho lead** (`app/…` normalize phone), không viết
hàm thứ hai — hai hàm chuẩn hoá là hai hàm sẽ lệch nhau (§12.2 vault: "lọc một chỗ").

### 2.2 KHÔNG BAO GIỜ gộp customer chỉ vì trùng email

Email **không phải** danh tính. Một người có thể dùng chung email công ty; một người
có thể đổi email. Gộp theo email sẽ **nhập hai khách khác nhau làm một** — và đó là
loại sai không sửa được về sau, vì dữ liệu đã trộn.

Email chỉ dùng để **làm giàu** hồ sơ, không dùng để **nhận diện**.

### 2.3 Quan hệ

```
leads.customer_id  →  customers.id   (nullable, có index)
customers 1 ─── n leads              (một khách, nhiều vết)
customers 1 ─── n customer_devices
customers 1 ─── 1 customer_acquisition   (UNIQUE customer_id — first-touch)
```

### 2.4 Thiết bị

`customer_devices` ghi **máy khách đang dùng**. Bội số: một khách nhiều máy.

**Phát hiện kỹ thuật phải xử lý (đã đo, không suy đoán):**

```
app/services/leads.py:99    iphone_model=model.display_name
app/models.py:68-69         model_code: String(64)   display_name: String(120)
```

`leads.iphone_model` lưu **TÊN HIỂN THỊ** (`"iPhone 16 Pro Max"`), **không phải**
`model_code` (`iphone-16-pro-max`). Hệ quả:

- `customer_devices.model_code` **không thể** lấy thẳng từ `leads.iphone_model`.
- Backfill **bắt buộc** `JOIN iphone_models ON display_name = leads.iphone_model`.
- `display_name` **KHÔNG có ràng buộc UNIQUE** ⇒ join có thể ra **0 hoặc >1 dòng**.
  Backfill phải chịu được cả hai: không khớp ⇒ để `model_code = NULL` và **ghi log**;
  khớp nhiều ⇒ lấy dòng `sort_order` nhỏ nhất (quy tắc xác định) và **ghi log**.

Đây là chỗ dễ hỏng im lặng nhất của G13. Nếu backfill dùng `JOIN` thường, dòng không
khớp sẽ **biến mất không một tiếng động** — đúng dạng "hỏng im lặng" mà vault đã ghi
thành luật. Nên migration **phải** dùng `LEFT JOIN` + đếm + in ra số dòng không khớp.

**Chính sách máy chính:** `is_primary = TRUE` cho máy của **lead MỚI NHẤT** của khách.
Ràng buộc: `UNIQUE (customer_id) WHERE is_primary` (partial index) — đảm bảo **đúng một**
máy chính mỗi khách, và biến việc "vô tình có hai máy chính" thành lỗi bắt được.

**Chống trùng thiết bị:** `UNIQUE (customer_id, model_code)` — cùng khách, cùng model
⇒ một dòng. Máy khác màu/ dung lượng **không** tạo dòng mới ở G13 (chưa có nhu cầu);
`color`/`storage` để nullable cho G14+.

### 2.5 Acquisition — first-touch, một dòng mỗi khách

Ghi lần đầu khách xuất hiện. Lead sau **không** ghi đè (giữ nguyên nguồn gốc — đó là
giá trị của nó). Ngoại lệ: trường đang `NULL` thì được điền, **không** được ghi đè
giá trị đã có.

`first_gift_code` = gift code của lead đầu tiên.

### 2.6 Consent thuộc về CUSTOMER

`customers.marketing_consent` + `consent_updated_at`.

**Quy tắc cập nhật:** consent là **một chiều trong G13** — chỉ được **bật lên** khi
lead mới nhất đồng ý, **không tự tắt**. Lý do: tắt consent là hành động pháp lý, phải
do người thật quyết (hoặc luồng huỷ đăng ký riêng), không phải hệ quả phụ của việc
một lead không tích ô. Nếu lead mới không tích, consent **giữ nguyên** trạng thái cũ.

### 2.7 Cập nhật khi có xung đột — không ghi đè lịch sử

| Trường | Luật |
|---|---|
| `phone_normalized` | khoá danh tính — không đổi |
| `full_name` | chỉ điền khi đang `NULL`; ngược lại **giữ nguyên** |
| `email` | chỉ điền khi đang `NULL` |
| `company_name`, `bni_chapter` | chỉ điền khi đang `NULL` |
| `marketing_consent` | chỉ bật, không tắt |

**Vì sao không ghi đè:** lead mới có thể là người nhà đặt hộ, ghi tên khác. Ghi đè là
âm thầm sửa lịch sử. Giữ bản gốc, và nếu sau này cần chính xác hơn thì có `leads` làm
nguồn đối chiếu.

### 2.8 Backfill lead cũ — bảo toàn tuyệt đối

- **Không xoá, không sửa** dòng `leads` nào. Chỉ **thêm** `customer_id`.
- Thứ tự xác định: `ORDER BY created_at, id`.
- **Idempotent / restart-safe:** dùng `ON CONFLICT (phone_normalized) DO NOTHING` cho
  `customers`; `customer_id` chỉ điền khi `IS NULL`. Chạy lại migration cho kết quả y hệt.
- Trước khi chạy: ghi lại **số dòng `leads`**. Sau khi chạy: **đếm lại**, phải bằng nhau.
  Không bằng ⇒ migration phải **nổ**, không được im lặng đi tiếp.

### 2.9 Gộp customer (merge) — KHÔNG làm ở G13

Cố ý **không** làm. Gộp hai khách là thao tác **không thể hoàn tác** và cần chính sách
của Owner (gộp đơn hàng thế nào? giữ gift code nào? consent lấy bên nào?). Làm ẩu rồi
sửa còn tệ hơn không làm. Ghi thành việc mở, chờ Owner quyết.

### 2.10 Rollback / forward-fix

`downgrade()`: xoá 3 bảng + cột `customer_id` trên `leads`.
**Dữ liệu `leads` còn nguyên** — vì bảng `leads` không hề bị sửa ngoài việc thêm cột.
Đây là lý do thiết kế này rollback được an toàn.

Nếu đã chạy trên staging rồi mà phát hiện sai: **không viết lại migration đã áp dụng** —
thêm migration mới bù (`0007_…`). Đúng luật migration của dự án.

## 3. Phương án đã cân nhắc và loại

| Phương án | Loại vì |
|---|---|
| Dùng `leads.phone` làm danh tính luôn, không tạo bảng | Không gắn được nhiều lead vào một khách; không có chỗ để máy/consent/acquisition |
| Gộp theo email khi có | Nhập nhầm hai khách — sai không sửa được (§2.2) |
| Thêm cột vào `leads`, không tách bảng | `leads` là vết lịch sử bất biến; nhồi trạng thái sống vào đó làm hỏng cả hai vai |
| `model_code` lấy thẳng từ `leads.iphone_model` | **Sai dữ liệu** — đó là tên hiển thị (§2.4) |

## 4. Ảnh hưởng tới hệ thống hiện có

- Funnel quà tặng **không đổi hành vi**. `create_lead` chỉ **thêm** bước liên kết
  customer; nếu bước đó lỗi thì lead **vẫn phải** được tạo (liên kết là phụ, không
  được làm hỏng đường chính) — nhưng lỗi phải **được ghi log**, cấm nuốt lỗi.
- 258 test hiện có **phải tiếp tục xanh**. Đây là điều kiện chặn.
- Không đụng `main`, không đụng production.

## 5. Kiểm chứng sẽ chạy

11 test bắt buộc + **3 đối chứng âm** (phá chuẩn hoá SĐT · phá UNIQUE · mở public endpoint)
+ đếm DB thật trên staging. Chi tiết ở issue G13.

## 6. Việc mở cho Owner

| # | Việc | Vì sao cần Owner |
|---|---|---|
| 1 | **Chính sách gộp customer** | Không thể hoàn tác; cần luật nghiệp vụ |
| 2 | Consent có được **tắt** qua lead không | Đây là quyết định pháp lý, không phải kỹ thuật |
| 3 | Một khách nhiều máy — có cần giữ lịch sử máy cũ không | Ảnh hưởng G15 (gợi ý phụ kiện) |
