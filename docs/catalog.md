# Danh mục sản phẩm (Product Catalog) — thiết kế G14

> **Viết TRƯỚC khi code.** Tài liệu này là quyết định; mã nguồn là hệ quả.
> Nguồn chân lý triển khai là **migration Alembic** (`migrations/versions/0007_*.py`).
> Khi tài liệu và migration lệch nhau: **tin migration**, và sửa tài liệu trong cùng PR.
>
> - **Gate:** G14 — Product Catalog
> - **Issue:** [#58](https://github.com/thanhbn123/vipphone/issues/58)
> - **Baseline:** `develop` = `db84838415920ef5c52f8d24e4c06d1d52aff199`, migration head `0006_customer_foundation`
> - **Ngày:** 2026-10-08
> - **Liên quan:** [`adr/0001-stack-selection.md`](adr/0001-stack-selection.md) · [`adr/0002-customer-identity.md`](adr/0002-customer-identity.md) · [`MASTER_STATUS.md`](MASTER_STATUS.md)

---

## 1. Vấn đề

Tới hết G13, hệ thống chỉ có **danh mục iPhone** (`iphone_models`) — tức là biết *khách đang
dùng máy nào*, nhưng **không có khái niệm "món hàng"**. Hệ quả:

- Không có chỗ để nói "ốp iPhone 16 Pro Max này bán 250.000đ" — giá không tồn tại ở đâu cả.
- Không có SKU ⇒ không thể nối với kho, với đơn hàng (G16), hay với bất kỳ kênh bán nào.
- Không có chỗ để nói "phụ kiện này dùng được cho những máy nào".

G14 dựng **danh mục sản phẩm**: category → product → SKU (biến thể) → tương thích thiết bị,
kèm API công khai, API quản trị, và hai trang UI tối thiểu.

G14 **cố ý KHÔNG** làm: kho hàng, giỏ hàng, đơn hàng, thanh toán, ảnh sản phẩm.
Xem §8 để biết chính xác cái gì nằm ngoài phạm vi.

---

## 2. Mô hình dữ liệu

Quan hệ: **một** category có **nhiều** product; **một** product có **nhiều** SKU;
**một** SKU tương thích với **nhiều** thiết bị.

```
categories 1 ─── n products 1 ─── n product_variants (SKU) 1 ─── n device_compatibility
```

### 2.1 `categories` — nhóm hàng

| Cột | Kiểu | Null | Ghi chú |
|---|---|---|---|
| `id` | `bigint` identity | no | khoá kỹ thuật nội bộ, **không** lộ ra API công khai |
| `code` | `varchar(40)` | no | **UNIQUE** — slug ổn định (`CASE`, `CHARGER`, …) |
| `name` | `varchar(120)` | no | tên hiển thị tiếng Việt |
| `sort_order` | `integer` | no | mặc định `0`, nhỏ đứng trước |
| `active` | `boolean` | no | mặc định `true` |
| `created_at` / `updated_at` | `timestamptz` | no | `now()` |

**Vì sao `code` là slug chữ HOA, không phải số:** code là thứ xuất hiện trong URL lọc, trong
cấu hình seed, và trong câu lệnh kiểm tra trên staging. Một con số (`1`) không nói lên điều gì
khi đọc log; `CHARGER` thì nói ngay. Chữ HOA để phân biệt rõ với slug sản phẩm (chữ thường).

### 2.2 `products` — sản phẩm

| Cột | Kiểu | Null | Ghi chú |
|---|---|---|---|
| `id` | `bigint` identity | no | khoá nội bộ |
| `product_id` | `uuid` | no | **UNIQUE** — định danh công khai, cùng nếp với `leads.lead_id` |
| `name` | `varchar(160)` | no | |
| `slug` | `varchar(160)` | no | **UNIQUE** — dùng cho `/product/{slug}` |
| `description` | `text` | yes | |
| `brand` | `varchar(80)` | yes | |
| `category_id` | `bigint` FK → `categories.id` | no | `ON DELETE RESTRICT` |
| `active` | `boolean` | no | mặc định `true` |
| `created_at` / `updated_at` | `timestamptz` | no | |

### 2.3 `product_variants` — SKU (biến thể bán được)

| Cột | Kiểu | Null | Ghi chú |
|---|---|---|---|
| `id` | `bigint` identity | no | |
| `sku` | `varchar(64)` | no | **UNIQUE** — mã hàng, chữ HOA/số/gạch |
| `product_id` | `bigint` FK → `products.id` | no | `ON DELETE CASCADE` |
| `variant_name` | `varchar(120)` | no | ví dụ `Đen — nhám` |
| `color` | `varchar(40)` | **yes** | màu là thuộc tính phụ, không phải danh tính |
| `cost_price` | `numeric(12,2)` | **yes** | **giá nhập — NỘI BỘ, không bao giờ trả ra công khai** |
| `sale_price` | `numeric(12,2)` | no | giá bán |
| `compare_at_price` | `numeric(12,2)` | **yes** | giá gạch |
| `currency` | `varchar(3)` | no | mặc định `VND` |
| `active` | `boolean` | no | mặc định `true` |
| `stock_tracking` | `boolean` | no | mặc định `false` — chỉ là **cờ**, xem §5 |
| `created_at` / `updated_at` | `timestamptz` | no | |

### 2.4 `device_compatibility` — máy nào dùng được SKU nào

| Cột | Kiểu | Null | Ghi chú |
|---|---|---|---|
| `id` | `bigint` identity | no | |
| `sku_id` | `bigint` FK → `product_variants.id` | no | `ON DELETE CASCADE` |
| `device_brand` | `varchar(40)` | no | mặc định `Apple` |
| `device_model_code` | `varchar(64)` | no | **khớp `iphone_models.model_code`** (ví dụ `iphone-16-pro-max`) |
| `compatibility_type` | `varchar(20)` | no | `FULL` / `PARTIAL` / `CASE_FIT` — có CHECK |
| `created_at` | `timestamptz` | no | |

**UNIQUE `(sku_id, device_brand, device_model_code)`** — cùng một SKU không khai hai lần cho
cùng một máy. Không có ràng buộc này thì khai trùng tích luỹ dần và không ai phát hiện.

---

## 3. Quyết định thiết kế và LÝ DO

### 3.1 TIỀN dùng `Numeric(12,2)` / `Decimal` — TUYỆT ĐỐI không `float`

Đây là quyết định quan trọng nhất của G14 và **không có ngoại lệ**.

`float` là số nhị phân: `0.1 + 0.2 == 0.30000000000000004`. Với tiền, sai số đó **không sửa
được về sau**, vì giá đã ghi vào đơn hàng, đã in hoá đơn, đã đối soát với kế toán. Không có
migration nào vá được một con số đã bán cho khách.

`Numeric(12,2)` là số thập phân chính xác: tối đa 10 chữ số phần nguyên + **đúng 2** chữ số
thập phân (tối đa `9999999999.99`). Đủ cho mọi mức giá của một cửa hàng phụ kiện, và **không
bao giờ** sinh sai số.

Có test khẳng định: ghi `250000.10` rồi đọc lại **đúng bằng** `Decimal("250000.10")`, và
`Decimal` cộng trừ ra kết quả chính xác (đối chứng âm: cùng phép tính với `float` cho ra
kết quả KHÁC — chứng minh phép đo phân biệt được).

### 3.2 Ràng buộc ở **tầng DB**, không chỉ ở tầng ứng dụng

`slug`, `product_id`, `sku`, `code` category đều UNIQUE **ở DB**, không chỉ kiểm bằng `SELECT`
rồi `INSERT`. Lý do đã trả giá ở chính sách chống trùng gift và ở `customers.phone_normalized`
(ADR-0002 §2.1): **hai request đồng thời** cùng `SELECT` thấy "chưa có" rồi cùng `INSERT` ⇒
hai dòng trùng. Ràng buộc chỉ ở ứng dụng **không chặn được cuộc đua**; UNIQUE ở DB biến nó
thành một lỗi bắt được, và router xử lý bằng **409** kèm thông báo rõ.

Đối chứng âm #2 của gate chứng minh điều này: gỡ UNIQUE `sku` ⇒ test UNIQUE **ĐỎ**.

### 3.3 `compare_at_price` không được nhỏ hơn `sale_price`

CHECK ở DB: `compare_at_price IS NULL OR compare_at_price >= sale_price`.

Giá gạch nhỏ hơn giá bán là **nói dối khách hàng** ("giảm giá" từ 100k xuống 200k) và là hành
vi bị luật bảo vệ người tiêu dùng chặn. Chặn ở DB để không phụ thuộc vào việc mọi đường ghi
đều nhớ kiểm.

### 3.4 `product_id` UUID song song `id` bigint

Cùng nếp `leads.lead_id` (UUID) + `leads.id` (bigint): **id nội bộ không lộ ra ngoài**, UUID
là định danh công khai. Nhờ vậy không ai dò được quy mô danh mục bằng cách đếm id, và đổi
khoá kỹ thuật sau này không phá tham chiếu bên ngoài.

### 3.5 `device_compatibility` trỏ tới **SKU**, không trỏ tới product

Một product có nhiều SKU, và các SKU **có thể** tương thích khác nhau: ốp trong suốt cho
iPhone 15 có thể không vừa iPhone 16, dù cùng là "ốp". Gắn compatibility vào product là ép
một sự thật sai — và sai theo hướng **khách mua nhầm**, loại sai đắt nhất.

### 3.6 `device_model_code` là **mã**, không phải tên hiển thị

Trường này khớp `iphone_models.model_code` (`iphone-16-pro-max`), **KHÔNG** khớp
`iphone_models.display_name` (`iPhone 16 Pro Max`).

**Vì sao phải nói rõ:** bài học đã trả giá ở G13 — `leads.iphone_model` lưu **tên hiển thị**,
và `display_name` **không có UNIQUE** (ADR-0002 §2.4), nên mọi join qua nó phải chịu được
**0 hoặc >1 dòng**. Ở G14 ta đi ngược lại: dùng **mã** làm khoá join. Hệ quả tích cực: lọc
theo thiết bị là so sánh chuỗi chính xác, không cần join, nên **không thể** nhân bản dòng.

Đánh đổi đã biết: `device_model_code` **không** có FK cứng tới `iphone_models.model_code`.
Lý do: (a) cho phép khai phụ kiện cho máy chưa có trong danh mục (ví dụ máy Android, hoặc
model sắp ra), (b) FK cứng sẽ chặn việc admin tắt một model — điều không liên quan gì tới
tương thích. **Rủi ro ghi ra:** có thể khai một `device_model_code` gõ sai mà không ai báo.
Cách vá đúng (chưa làm ở G14, ghi thành việc mở): cảnh báo ở tầng admin khi code không khớp
`iphone_models`, và báo cáo định kỳ các code mồ côi.

### 3.7 `stock_tracking` là **cờ**, không phải tồn kho

`stock_tracking = true` nghĩa là *"SKU này, về nguyên tắc, sẽ được theo dõi tồn kho khi có
inventory engine"*. **Chưa có inventory engine** ⇒ cờ này hiện **không** sinh ra số lượng nào.

Ghi rõ ra đây vì đây là chỗ dễ tự lừa nhất: một cột tên `stock_tracking` rất dễ bị đọc thành
"đang có hàng". Nó không phải vậy. Xem §5.

### 3.8 Xoá: RESTRICT ở category, CASCADE ở SKU/compatibility

- `products.category_id → categories.id` **RESTRICT**: xoá một category còn sản phẩm là hành
  động phá dữ liệu — chặn, và admin phải chuyển sản phẩm sang category khác trước. Muốn "ẩn"
  category thì đặt `active = false`, **không xoá**.
- `product_variants.product_id` và `device_compatibility.sku_id` **CASCADE**: SKU là bộ phận
  của product, compatibility là bộ phận của SKU. Xoá cha thì con không còn nghĩa lý.

### 3.9 Migration `0007` là **additive**, có `downgrade` thật

Không sửa một dòng nào của migration `0001`–`0006` (luật dự án: **cấm viết lại migration đã
áp dụng**). `0007` chỉ `CREATE TABLE` + `INSERT` seed category.

`downgrade()` xoá 4 bảng theo đúng thứ tự phụ thuộc. Dữ liệu `0001`–`0006` **không bị đụng**,
nên rollback G14 không ảnh hưởng lead/khách/gift.

### 3.10 Seed: **10 category, deterministic, idempotent** — và **0 sản phẩm**

10 code: `CASE`, `SCREEN_PROTECTOR`, `CABLE`, `CHARGER`, `POWER_BANK`, `EARPHONE`, `MAGSAFE`,
`CAR_ACCESSORY`, `STAND`, `OTHER`.

- **Deterministic:** danh sách viết cứng trong migration, `sort_order` theo đúng thứ tự trên.
  Chạy hai lần cho kết quả y hệt.
- **Idempotent:** `ON CONFLICT (code) DO NOTHING`. Chạy lại sau khi admin đã sửa tên category
  **không ghi đè** tên admin đặt — seed chỉ tạo cái còn thiếu.
- **KHÔNG seed sản phẩm nào.** Danh mục category là *từ vựng* (hệ thống cần nó để phân loại);
  sản phẩm là *dữ liệu kinh doanh* (chỉ có thật khi người thật nhập giá thật).

**Vì sao không seed sản phẩm "cho đẹp":** một sản phẩm giả có giá giả, nằm lẫn trong danh mục
thật, sẽ bị đối xử như dữ liệu thật — hiện lên `/shop`, lọt vào báo cáo, và có ngày bị bán.
Đây đúng luật chống bịa. Nếu cần dữ liệu để **nghiệm thu staging**, dùng marker nói thẳng nó
là gì: `DEMO-STAGING` trong tên + `source=staging-commerce-test`, và **xoá sau nghiệm thu**.

---

## 4. Luật giá

| Luật | Ép ở đâu | Vì sao |
|---|---|---|
| `sale_price >= 0` | CHECK DB + schema | giá âm là lỗi dữ liệu, không phải khuyến mãi |
| `cost_price >= 0` khi có | CHECK DB + schema | như trên |
| `compare_at_price >= sale_price` khi có | CHECK DB + schema | §3.3 |
| `currency` = 3 chữ HOA | schema (`^[A-Z]{3}$`) + mặc định `VND` | tránh `vnd`/`Vnd`/`VNĐ` thành ba loại tiền |
| Tiền là `Decimal`, **không** `float` | kiểu cột DB + schema | §3.1 |
| Public **không** trả `cost_price` | schema công khai riêng | §5.2 |

**Chưa làm ở G14 (nói thẳng):** lịch sử giá (giá đổi lúc nào, ai đổi), giá theo số lượng,
giá theo kênh, thuế/phí. Ghi thành việc mở.

---

## 5. Luật hiển thị: công khai vs quản trị

### 5.1 Ranh giới là **dữ liệu trả về**, không phải giao diện

| | Công khai | Quản trị |
|---|---|---|
| Product `active = false` | **KHÔNG BAO GIỜ** thấy | thấy (để bật lại) |
| SKU `active = false` | **KHÔNG BAO GIỜ** thấy | thấy |
| Category `active = false` | chỉ thấy nếu còn sản phẩm active (không lọc theo category đó nữa) | thấy |
| `cost_price` | **KHÔNG BAO GIỜ** | thấy |
| `product_id` (UUID) | có | có |
| `id` bigint nội bộ | **không** | có |
| Nhãn `availability` | `IN_STOCK` / `OUT_OF_STOCK` (không bao giờ là số) | như công khai + thấy SKU đã tắt |
| Xác thực | không cần khoá | **bắt buộc** `Depends(require_staff)` |

Hai lược đồ Pydantic **tách hẳn** (`ProductOut` vs `AdminProductOut`), vì dùng chung một lược
đồ rồi "ẩn bớt trường" là cách chắc chắn nhất để một ngày nào đó trường nội bộ lọt ra ngoài.
`AdminProductOut` kế thừa `ProductOut` và **thêm** trường — chiều kế thừa có kiểm soát, không
phải chiều ngược lại.

### 5.2 `cost_price` là ranh giới bảo mật, không phải chuyện thẩm mỹ

Lộ giá nhập cho đối thủ = lộ toàn bộ biên lợi nhuận. Có test khẳng định **chuỗi JSON công
khai không chứa** khoá `cost_price` (kiểm trên cả danh sách lẫn chi tiết) — không kiểm bằng
mắt.

### 5.3 `require_staff` **fail CLOSED**, không ngoại lệ

**Mọi** route `/api/admin/products*` đều có `Depends(require_staff)`, **kể cả route chỉ đọc**.
Chưa cấu hình `STAFF_API_KEYS` ⇒ **503**, không mở toang (xem `app/security.py`).

Vì sao viết thành câu: một route quên dependency thì **không có gì báo lỗi** — nó vẫn trả 200,
chỉ khác là ai cũng đọc được. Có test auth boundary cho **từng** route admin của G14 (cả
`GET`, `POST`, `PATCH`, `DELETE`), và đối chứng âm ghi cách phá.

### 5.4 Bộ lọc công khai — áp `active` ở **cả hai tầng**

`GET /api/products` chỉ trả product **và** SKU active. Bộ lọc `active` áp ở **một chỗ duy
nhất** trong service (`public_product_query`) để danh sách và chi tiết **không thể** lệch nhau
— nếu lọc hai nơi, bản vá thứ hai sẽ vô tác dụng dù mã trông đúng (§12.2 vault).

Chi tiết `/api/products/{slug}`: product không active ⇒ **404** (không phải 403, không phải
200-kèm-rỗng). 200-kèm-rỗng khiến UI tưởng đã lấy được hàng; 403 xác nhận sự tồn tại của slug
— 404 không xác nhận gì.

---

## 6. Compatibility hoạt động thế nào

### 6.1 Khai báo

Admin khai cho **từng SKU**: SKU này dùng được cho máy `device_model_code` nào, với mức
tương thích nào.

| `compatibility_type` | Nghĩa |
|---|---|
| `FULL` | vừa hoàn toàn, đúng thiết kế |
| `PARTIAL` | vừa nhưng có lưu ý (che camera lệch nhẹ, không vừa ốp dày…) |
| `CASE_FIT` | chỉ vừa khi đã có ốp (dùng cho miếng dán, giá đỡ) |

`PARTIAL` tồn tại vì thực tế phụ kiện không phải nhị phân. Bỏ nó đi thì admin buộc phải chọn
sai (`FULL` khi thật ra không hoàn toàn) — và dữ liệu sai âm thầm còn tệ hơn không có dữ liệu.

### 6.2 Lọc

`GET /api/products?device_model=iphone-16-pro-max` trả về đúng những product **có ít nhất một
SKU active** tương thích với máy đó.

Dùng **`EXISTS` (bán kết nối)**, không dùng `JOIN`:

```sql
WHERE EXISTS (SELECT 1 FROM product_variants v
              JOIN device_compatibility dc ON dc.sku_id = v.id
              WHERE v.product_id = products.id AND v.active
                AND dc.device_brand = :brand AND dc.device_model_code = :code)
```

**Vì sao `EXISTS` chứ không `JOIN`:** một product có 3 SKU cùng tương thích với một máy thì
`JOIN` trả **3 dòng trùng** cho cùng một product — danh sách phình ra, `total` phân trang sai,
và khách thấy cùng một món ba lần. `EXISTS` dừng ở lần khớp đầu tiên nên **không thể** nhân
bản dòng. Đây là cùng loại lỗi với `display_name` không UNIQUE ở G13, nhưng lần này chặn
được bằng cấu trúc truy vấn.

Đối chứng âm #3 của gate chứng minh điều này: phá nhánh lọc compatibility ⇒ test lọc theo
thiết bị **ĐỎ**.

### 6.3 Không có FK cứng — hệ quả đã biết

Xem §3.6: `device_model_code` không FK tới `iphone_models`. Nghĩa là **có thể** khai một mã
gõ sai và hệ thống không báo. Việc mở: cảnh báo ở admin + báo cáo mã mồ côi.

---

## 7. UI

### 7.1 Trang

| Trang | Nội dung |
|---|---|
| `/shop` | danh sách product, lọc theo category · thiết bị · từ khoá, phân trang |
| `/product/{slug}` | chi tiết product, danh sách SKU, máy tương thích, CTA |

Mobile-first: danh sách là một cột ở 320px, giãn thành lưới ở màn rộng. Không tràn ngang ở
320/375/390/430px (đo bằng E2E thật).

### 7.2 Hiện gì

Tên · giá · category · máy tương thích · trạng thái (Còn hàng / Hết hàng) · CTA.

### 7.3 **Còn hàng / Hết hàng — TUYỆT ĐỐI KHÔNG bịa số lượng**

G14 **chưa có inventory engine**. Vì vậy UI **không được** hiện "còn 7 chiếc", "sắp hết",
"chỉ còn 2" — mọi con số như vậy sẽ là **bịa**.

**Trường `availability` nằm ở CẤP SẢN PHẨM** (không phải ở từng SKU), vì đường công khai
chỉ trả SKU `active` — nếu đặt ở SKU thì nó sẽ luôn cùng một giá trị và trở thành trường chết:

| Giá trị | Điều kiện | UI |
|---|---|---|
| `IN_STOCK` | sản phẩm `active` **và** có **ít nhất một** SKU `active` | **Còn hàng** |
| `OUT_OF_STOCK` | sản phẩm `active` nhưng **không** còn SKU `active` nào | **Hết hàng** |

Sản phẩm `active = false` **không xuất hiện** ở đường công khai (⇒ 404 ở chi tiết), nên nó
không có nhãn nào để hiện.

Trường `stock_tracking` **không** tham gia vào việc suy ra hai nhãn này, và điều đó phải giữ
nguyên cho tới khi có inventory engine thật. Khi nào có, sửa **tài liệu này trước**, rồi mới
sửa UI.

### 7.4 Ràng buộc kỹ thuật bắt buộc

- **Không hard-code sản phẩm trong HTML.** Mọi thứ đến từ API. (Danh mục iPhone cũng vậy —
  có chốt CI.)
- **Không inline script/style/handler.** CSP nghiêm `script-src 'self'` + `style-src 'self'`
  sẽ chặn; và có chốt CI quét `on*=` / `<script>…` / `style="`.
- **Không hotlink ảnh từ internet.** `img-src 'self' data:` chặn ở CSP, và hotlink làm rò IP
  khách sang bên thứ ba. G14 chưa có kho ảnh ⇒ UI **không hiện ảnh**, không thay bằng ảnh mượn.
- **Mọi nội dung chèn vào DOM phải escape.** Dùng `VPUtil.escapeHtml` (đã có, một bản duy
  nhất trong frontend).
- Trang mới phải có `lang="vi"` + `viewport` (chốt CI kiểm cả hai).

---

## 8. Nằm NGOÀI phạm vi G14 — nói thẳng

| # | Việc | Vì sao ngoài phạm vi |
|---|---|---|
| 1 | **Inventory engine** (số lượng tồn thật, giữ chỗ, trừ kho) | Không có ⇒ **không có số lượng tồn kho ở bất kỳ đâu**, kể cả admin. `stock_tracking` chỉ là cờ. |
| 2 | Giỏ hàng / đơn hàng / thanh toán | G16 |
| 3 | Ảnh sản phẩm (tải lên, lưu trữ, phục vụ) | Chưa có kho ảnh ⇒ UI không hiện ảnh, **không hotlink** thay thế |
| 4 | Lịch sử giá + audit thay đổi giá | Chưa cần cho G14; `audit_events` chưa có loại event cho catalog |
| 5 | Đồng bộ tồn kho/giá với kênh bán ngoài | Chưa có kênh nào |
| 6 | FK cứng `device_model_code → iphone_models.model_code` | Cố ý không làm — xem §3.6, kèm rủi ro đã ghi |
| 7 | Cảnh báo `device_model_code` gõ sai | Việc mở — xem §6.3 |
| 8 | Gộp/đổi SKU đã bán | Không thể hoàn tác — cần luật nghiệp vụ của Owner |

---

## 9. Kiểm chứng sẽ chạy

Trong `tests/test_product_catalog.py`:

1. migration chạy được + đúng 10 category + `slug`/`sku` UNIQUE ở DB
2. product/SKU inactive **ẩn** khỏi danh sách công khai
3. SKU inactive **ẩn** khỏi chi tiết công khai; product inactive ⇒ **404**
4. admin **thấy** inactive
5. `sku` UNIQUE (DB) · `slug` UNIQUE (DB)
6. giá là `Decimal`, không sai số float
7. lọc compatibility theo `device_model` — và **không nhân bản dòng** khi nhiều SKU cùng khớp
8. keyword search (`q`) theo tên và theo SKU
9. `cost_price` **không** xuất hiện trong JSON công khai
10. auth boundary cho **mọi** route admin (401 khi thiếu khoá, 401 khi khoá sai, 200 khi đúng)
11. phân trang: `total` đúng, `page_size` có trần
12. `compare_at_price < sale_price` bị chặn (DB CHECK)
13. category `RESTRICT`: không xoá được category còn sản phẩm
14. UI `/shop` + `/product/{slug}` trả 200, có `lang="vi"` + viewport, **không** inline
    script/style/handler

Và **3 đối chứng âm** — phá đúng thứ đang được bảo vệ, test phải ĐỎ:

| # | Phá gì | Test phải đỏ |
|---|---|---|
| 1 | Bỏ điều kiện `active` trong truy vấn công khai | test inactive ẩn khỏi public |
| 2 | Gỡ UNIQUE `sku` | test `sku` UNIQUE |
| 3 | Bỏ nhánh lọc compatibility | test lọc theo `device_model` |

Cách phá + kết quả đo ghi vào `MASTER_STATUS.md`, không chỉ nói "đã có đối chứng âm".
