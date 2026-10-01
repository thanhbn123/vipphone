# VIP PHONE — MASTER STATUS

> **Nguồn trạng thái chính của dự án VIP PHONE.**
> Mọi gate phải cập nhật file này trước khi mở gate kế tiếp.
>
> **Luật:** không ghi PASS / DONE / READY nếu không có evidence đo được.
> Chưa chạy thì ghi `NOT RUN`. Chưa deploy thì ghi `NOT DEPLOYED`.
> Kết luận dạng "0 lỗi" phải ghi kèm **công cụ đo**, **phạm vi đo** và **cái nằm ngoài phạm vi**.

- Cập nhật lần cuối: **2026-10-01, 19:21 +07**
- Người cập nhật: DEEPSEEK HARNESS — VIP PHONE PROJECT CONTROLLER
- Gate vừa xong: **G04 + G05 + G06** (issue [#7](https://github.com/thanhbn123/vipphone/issues/7), PR [#8](https://github.com/thanhbn123/vipphone/pull/8), merge `280ef00`)
- `main`: `7d6162cf31eb96ea27879be3a4671812a9cd7e01` — **KHÔNG ĐỔI suốt cả gate**
- **Merge SHA của gate này vào `develop`: `280ef0026f0904d87ac03b95c01170e2c9ee9f64`**
  (đỉnh `develop` KHÔNG được ghi ở đây — chính commit tài liệu này làm nó đổi; đọc bằng
  `git rev-parse origin/develop`. Ghi một giá trị sẽ hết đúng ngay sau khi ghi.)
- Repo: <https://github.com/thanhbn123/vipphone>

---

## 1. TRẠNG THÁI GATE

| Gate | Nội dung | Trạng thái | PR | CI | Merge SHA vào develop |
|---|---|---|---|---|---|
| Phase 0 | Discovery / Baseline | **DONE** | — | — | — |
| G01 | Baseline hardening + sửa CI đỏ | **DONE** | [#2](https://github.com/thanhbn123/vipphone/pull/2) | **PASS** | `7dabe0ade68797a6eead65dd315924f52748987a` |
| G02 | Real backend (API + DB + migration + QR chuẩn + catalog) | **DONE** | [#4](https://github.com/thanhbn123/vipphone/pull/4) | **PASS** | `b4ca55d3bedcf67c910d0223029da92e37ed6492` |
| G03 | Redeem engine (atomic, chống double-spend) + audit | **DONE** | [#6](https://github.com/thanhbn123/vipphone/pull/6) | **PASS** | `92a4952d54c1d2009a85f69ba74a44becc4651df` |
| G04+G05+G06 | Staff redeem UI (quét QR) + Admin leads/CSV + Danh mục iPhone qua admin | **DONE** | [#8](https://github.com/thanhbn123/vipphone/pull/8) | **PASS — 3/3 job** | `280ef0026f0904d87ac03b95c01170e2c9ee9f64` |
| G07 | Campaign / source tracking | MỘT PHẦN (đã có ở G02: nhận & lưu ở server) | — | — | — |
| G08 | Security pass | MỘT PHẦN (đã có ở G02 + **G05: IDOR, CSV injection**; còn Turnstile/dependency scan) | — | — | — |
| G09 | Tests đầy đủ | MỘT PHẦN (280 backend + **14 E2E trình duyệt thật**; E2E **chưa nối vào CI**) | — | — | — |
| G10 | CI đầy đủ | MỘT PHẦN (lint, migration, unit, integration PG, secret scan) | — | — | — |
| G11 | Staging readiness | MỘT PHẦN (`.env.example`, `/api/ready` đã có; `docs/deployment.md` chưa) | — | — | — |
| G12 | Owner acceptance pack | NOT STARTED | — | NOT RUN | — |

**Baseline gốc của dự án:** `7d6162cf31eb96ea27879be3a4671812a9cd7e01` (1 commit, 14 file, CI đỏ 2/2 run).
Chi tiết baseline đầy đủ nằm ở lịch sử git (`git show 7d6162c`) và ở PR #2.

### 1.1 Gate G04+G05+G06 — số đo

| Mục | Giá trị đo được | Cách đo |
|---|---|---|
| Issue | [#7](https://github.com/thanhbn123/vipphone/issues/7) | `gh issue list` |
| PR | [#8](https://github.com/thanhbn123/vipphone/pull/8) | `gh pr view 8` |
| Expected develop | `92a4952d54c1d2009a85f69ba74a44becc4651df` | `git rev-parse origin/develop` |
| Actual develop (trước merge) | `92a4952d54c1d2009a85f69ba74a44becc4651df` | `git rev-parse origin/develop` |
| Merge-base | `92a4952d54c1d2009a85f69ba74a44becc4651df` | `git merge-base origin/develop <PR HEAD>` |
| PR HEAD | `cd460d29c95bb2d7b9d700349bde91f8ed999f00` | `gh pr view 8 --json headRefOid` |
| **Merge SHA của gate vào `develop`** | **`280ef0026f0904d87ac03b95c01170e2c9ee9f64`** | `git rev-parse origin/develop` ngay sau khi merge PR #8 (2026-10-01, 19:19 +07) |
| `main` sau gate | `7d6162cf31eb96ea27879be3a4671812a9cd7e01` — **KHÔNG ĐỔI** | `git rev-parse origin/main` |
| PR chốt số | [#9](https://github.com/thanhbn123/vipphone/pull/9) (chỉ `docs/MASTER_STATUS.md`) | `gh pr view 9` |

> **Vì sao không ghi "đỉnh `develop` hiện tại":** tài liệu này nằm trong `develop`, nên mỗi lần
> cập nhật nó lại tạo một đỉnh mới — giá trị ghi ra sẽ sai ngay sau khi ghi. Ghi **merge SHA của
> gate** (bất biến) thay vì **đỉnh nhánh** (luôn đổi). Đây là cùng một luật với mục 12.1: chỉ
> được nói trong đúng phạm vi đo được, và ở đây phạm vi đo được là "thời điểm merge PR #8".

Drift: **expected == actual == merge-base** ⇒ không lệch, được phép merge.

**CI của PR #8 — đọc từng step, không suy từ dấu ✓ của job** (`gh run view --log --job=…`):

| Job | Kết luận | Bằng chứng đọc được từ log |
|---|---|---|
| `Secret scan (gitleaks)` | **PASS** (5 s) | 4/4 step chạy, gitleaks 8.30.1 quét toàn bộ lịch sử |
| `Validate static frontend` | **PASS** (7 s) | 10/10 step chạy, **không step nào bị skip** |
| `Backend (lint, migration, tests)` | **PASS** (56 s) | ruff: *All checks passed!* + *38 files already formatted*; unit: **57 passed, 223 deselected**; integration: **223 passed, 57 deselected**; full: **280 passed**, 0 failed, 0 skipped |

Con số trên CI khớp đúng con số đo ở máy (280 passed). Không có test nào bị skip.

---

## 2. QUYẾT ĐỊNH KIẾN TRÚC

| ADR | Quyết định | Trạng thái |
|---|---|---|
| [ADR-0001](adr/0001-stack-selection.md) | Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL 16 | **Accepted** |

---

## 3. KIẾN TRÚC HIỆN TẠI (sau G02)

```
Trình duyệt (HTML/CSS/JS thuần, KHÔNG build step)
   │
   ├── GET  /api/catalog/iphone-models   → danh mục iPhone
   ├── POST /api/leads                   → tạo lead + cấp gift code
   ├── GET  /api/gifts/{code}            → tra cứu cho nhân viên (cần xác thực)
   ├── GET  /api/gifts/{code}/qr.png     → ảnh QR chuẩn (công khai, không PII)
   ├── POST /api/gifts/{code}/redeem    → phát quà (nhân viên, nguyên tử)
   ├── GET  /api/admin/leads            → tra cứu lead (nhân viên)
   ├── GET  /api/admin/leads.csv        → export CSV (nhân viên)
   ├── GET  /api/admin/leads/{id}       → chi tiết lead (nhân viên)
   ├── GET/POST/PATCH /api/admin/iphone-models → danh mục iPhone (nhân viên)
   ├── GET  /api/health | /api/ready     → liveness / readiness
   │
   └── FastAPI  ──►  PostgreSQL 16 (Alembic migration)
```

- **Một tiến trình** phục vụ cả API lẫn file tĩnh → deploy/rollback đơn giản.
- Frontend **không có build step**, không framework.
- **Server là nguồn chân lý duy nhất cho lead.** `localStorage` không còn được dùng để lưu lead;
  CI có chốt chặn chống thoái hoá (grep `vipphone_leads_v1`).

---

## 4. DATABASE

Migration head: **`0001_initial`** (`migrations/versions/0001_initial.py`).

| Bảng | Vai trò |
|---|---|
| `leads` | Lead + gift code + trạng thái phát quà |
| `audit_events` | Audit trail |
| `iphone_models` | Danh mục iPhone |

### 4.1 Index trên `leads` — đo bằng `pg_indexes`

| Index | Cột | Loại |
|---|---|---|
| `uq_leads_lead_id` | `lead_id` | UNIQUE |
| `uq_leads_gift_code` | `gift_code` | UNIQUE |
| `uq_leads_active_duplicate` | `(phone, iphone_model)` | **UNIQUE MỘT PHẦN**, `WHERE gift_status <> 'CANCELLED'` |
| `ix_leads_phone` | `phone` | thường |
| `ix_leads_created_at` | `created_at` | thường |
| `ix_leads_gift_status` | `gift_status` | thường |
| `ix_leads_dup` | `(phone, iphone_model, gift_status)` | thường |

Kiểm tra ràng buộc (`pg_constraint`):

- `ck_leads_gift_status` — `NEW / CONFIRMED / READY / REDEEMED / CANCELLED`
- `ck_leads_consent_true` — `consent IS TRUE`
- `ck_leads_phone_canonical` — `phone ~ '^0[35789][0-9]{8}$'`

**Schema chỉ do Alembic tạo.** Ứng dụng **không** gọi `create_all()`.

---

## 5. API

| Method | Path | Xác thực | Trạng thái |
|---|---|---|---|
| GET | `/api/health` | công khai | **CÓ** — không truy vấn DB |
| GET | `/api/ready` | công khai | **CÓ** — kiểm DB + migration head + nói rõ phần chưa cấu hình |
| POST | `/api/leads` | công khai (+ rate limit, + Turnstile nếu cấu hình) | **CÓ** |
| GET | `/api/catalog/iphone-models` | công khai | **CÓ** |
| GET | `/api/gifts/{gift_code}` | **nhân viên** | **CÓ** |
| GET | `/api/gifts/{gift_code}/qr.png` | công khai | **CÓ** |
| POST | `/api/gifts/{gift_code}/redeem` | **nhân viên** | **CÓ** (G03) — nguyên tử, idempotent |
| GET | `/api/admin/leads` | **nhân viên** | **CÓ** (G05) — lọc, phân trang, tổng số |
| GET | `/api/admin/leads.csv` | **nhân viên** | **CÓ** (G05) — cùng bộ lọc, trần 5.000 dòng |
| GET | `/api/admin/leads/{lead_id}` | **nhân viên** | **CÓ** (G05) — chi tiết |
| GET | `/api/admin/iphone-models` | **nhân viên** | **CÓ** (G06) — cả model đã tắt |
| POST | `/api/admin/iphone-models` | **nhân viên** | **CÓ** (G06) |
| PATCH | `/api/admin/iphone-models/{model_code}` | **nhân viên** | **CÓ** (G06) |

### 5.1 Bộ lọc của `/api/admin/leads` (dùng CHUNG với `leads.csv`)

| Tham số | Kiểu | Ghi chú |
|---|---|---|
| `phone` | chuỗi | khớp MỘT PHẦN; chỉ giữ chữ số; `%`/`_` bị escape nên không thành ký tự đại diện |
| `iphone_model` | chuỗi | nhận `model_code` (UI gửi) hoặc tên hiển thị (dữ liệu đã lưu) |
| `source` | chuỗi | khớp chính xác |
| `gift_status` | chuỗi | một trong `NEW/CONFIRMED/READY/REDEEMED/CANCELLED`, sai → 422 |
| `created_from` | `YYYY-MM-DD` | từ 00:00 UTC |
| `created_to` | `YYYY-MM-DD` | **trọn ngày** (cận trên độc quyền = 00:00 UTC hôm sau) |
| `page` | số ≥ 1 | mặc định 1 |
| `page_size` | 1…200 | mặc định 50; vượt trần → **422**, không cắt im lặng |

Thứ tự: `created_at DESC, id DESC` — thêm `id` để thứ tự **tất định** khi trùng mốc thời gian
(thiếu nó thì hai trang liên tiếp có thể lặp hoặc sót hàng, và đó là lỗi im lặng).

`/api/admin/leads.csv` **không** nhận `page`/`page_size`; nó dùng chung hàm dựng truy vấn với
danh sách nên hai đường không thể lệch nhau. Có trần `CSV_MAX_ROWS = 5_000` và trả header
`X-VIPPHONE-CSV-Truncated: true` khi bị cắt — **không cắt im lặng**.

`POST /api/leads` trả về:

```json
{ "lead_id": "...", "gift_code": "VIP-26-XXXXXX", "gift_status": "NEW", "duplicate": false }
```

Lỗi có cấu trúc thống nhất:

```json
{ "error": { "code": "VALIDATION_FAILED", "message": "...", "fields": { "phone": "..." } } }
```

---

## 6. CHÍNH SÁCH CHỐNG TRÙNG

**Luật:** cùng `phone` (ĐÃ CHUẨN HOÁ) + cùng `iphone_model` + `gift_status <> 'CANCELLED'`
→ **trả lại gift hiện có**, KHÔNG tạo gift mới.

Ép ở **HAI tầng**:

1. **Tầng ứng dụng** (`app/services/leads.py`) — tra trước khi tạo.
2. **Tầng database** — `uq_leads_active_duplicate`, UNIQUE INDEX MỘT PHẦN. Hai request
   đồng thời cũng không tạo nổi hai gift; request thua cuộc bắt `IntegrityError`,
   tra lại và trả gift đang có.

Có test: gửi lại y hệt, gửi `+84…` so với `09…`, khác dòng máy, khác số, và
gift đã `CANCELLED` thì được cấp gift mới.

---

## 7. GIFT CODE

- Định dạng `VIP-YY-XXXXXX`.
- `YY` lấy từ `GIFT_CODE_YEAR_PREFIX`, **để trống thì suy từ năm hiện tại (UTC)** — không hard-code.
- Thân mã: CSPRNG (`secrets.choice`), alphabet 32 ký tự `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`
  (bỏ `I`, `O`, `0`, `1` để không đọc nhầm).
- Entropy: `32^6 ≈ 1,07 * 10^9` tổ hợp. Tăng được qua `GIFT_CODE_LENGTH`.
- **Không tuần tự, không suy từ `id`.**
- Tra cứu **không phân biệt hoa/thường**, tự bỏ khoảng trắng.
- Ràng buộc `UNIQUE` ở DB; đụng độ thì **thử lại** (tối đa `GIFT_CODE_MAX_ATTEMPTS`), không báo lỗi cho khách.

---

## 8. QR

| Mục | Trạng thái |
|---|---|
| Sinh QR | **Server**, thư viện `qrcode`, chuẩn **ISO/IEC 18004** |
| Endpoint | `GET /api/gifts/{code}/qr.png` |
| Nội dung | `<PUBLIC_BASE_URL>/redeem?code=<gift_code>` — **chỉ URL công khai** |
| PII trong QR | **KHÔNG** — có test giải mã QR thật để chứng minh |
| Domain | Lấy từ `PUBLIC_BASE_URL`, **không hard-code** trong mã nguồn |
| `qr-lite.js` (QR giả) | **ĐÃ GỠ**; CI chặn nếu quay lại |

**`QR = PASS`** — căn cứ: test `test_qr_decodes_to_public_redeem_url` và
`test_qr_contains_no_pii` giải mã ảnh PNG thật bằng **zxing-cpp** và so với URL mong đợi;
test `test_qr_decoder_can_tell_payloads_apart` là **đối chứng dương** chứng minh bộ giải mã
phân biệt được hai nội dung khác nhau (nếu không, phép đo vô nghĩa).

---

## 9. REDEEM

| Mục | Trạng thái |
|---|---|
| Tra cứu gift cho nhân viên | **CÓ** (G02), trả trường tối thiểu, SĐT che bớt |
| Xác nhận phát quà (ghi trạng thái) | **CÓ** (G03) |
| Chống double-spend | **CÓ** — `SELECT … FOR UPDATE`, chứng minh bằng test tất định |
| Idempotent | **CÓ** — đã REDEEMED thì trả `already_redeemed = true`, **không** đổi `redeemed_at` |
| Audit `GIFT_STATUS_CHANGED` + `GIFT_REDEEMED` | **CÓ**, ghi cùng transaction |
| Trạng thái được phép chuyển | `NEW` / `CONFIRMED` / `READY` → `REDEEMED`. `CANCELLED` → **409, không phát quà** |

### 9.1 Giao diện nhân viên (G04)

| Mục | Trạng thái |
|---|---|
| Nhập gift code, xem thông tin tối thiểu, xác nhận phát quà, hiện trạng thái đã redeem | **CÓ** |
| Quét QR bằng camera | **CÓ, có điều kiện** — dùng `BarcodeDetector` của chính trình duyệt, không nạp thư viện ngoài (CSP `script-src 'self'` sẽ chặn CDN) |
| Không hỗ trợ thì ẩn nút | **CÓ** — test E2E giả lập **cả hai** nhánh trình duyệt và đo DOM thật |
| Khoá nhân viên | chỉ `sessionStorage`, **không** `localStorage`/cookie/query string. UI ghi rõ khoá chỉ sống trong phiên |
| Dữ liệu trả về | tối thiểu: SĐT che (`0912***678`), không UTM, không công ty |
| Ranh giới xác thực | `require_staff`, **fail closed 503** — giữ nguyên từ G02 |

Nội dung QR khi quét: **chỉ nhận URL công khai `/redeem?code=…`** (đúng thứ server sinh ra).
QR lạ (ví dụ `https://evil.example/…`) → trang nói thẳng "không phải phiếu quà VIP PHONE",
**không** nhét mã rác vào ô và **không** gọi API tra cứu.

**Cơ chế chống double-spend:** `SELECT … FOR UPDATE` khoá hàng TRƯỚC khi đọc trạng thái.
Ở mức READ COMMITTED, transaction thứ hai **chờ**; khi được giải phóng, PostgreSQL đọc lại
hàng ĐÃ CẬP NHẬT nên bên thua thấy `REDEEMED` và trả idempotent thay vì ghi lần hai.

**Đo được (không suy đoán):** hai test **tất định** — (a) `locked_lead_query()` phải
compile ra SQL có `FOR UPDATE`, (b) khi hàng đang bị khoá, đọc `pg_stat_activity` phải thấy
backend của service đang chờ **Ở CHÍNH CÂU `SELECT … FOR UPDATE`** (không phải ở câu `UPDATE`).
Đã kiểm bằng **đối chứng âm**: bỏ `with_for_update()` thì **cả hai test FAIL**; khôi phục thì
**cả hai PASS**.

---

## 10. AUDIT LOG

Bảng `audit_events`: `event_id`, `event_type`, `lead_id`, `gift_code`, `actor`, `metadata` (JSONB), `created_at`.

Đã ghi: `LEAD_CREATED`, `GIFT_CREATED`. Sẽ thêm: `GIFT_STATUS_CHANGED`, `GIFT_REDEEMED` (G03).

`metadata` đi qua **DANH SÁCH TRẮNG khoá** (`app/audit.py`): khoá lạ bị **loại bỏ và ghi log**,
không được lưu. Có danh sách ĐEN riêng cho `phone`, `full_name`, `company_name`, `token`, `secret`…
`actor` của khách là `public:<ip>`; của nhân viên là `staff:<12 ký tự đầu SHA-256 của khoá>`
— định danh được **mà không lộ khoá**.

---

## 11. DANH MỤC IPHONE

- Bảng `iphone_models`: `year`, `model_code` (unique), `display_name`, `active`, `sort_order`.
- Seed trong migration: **28 model** đúng bằng `data/iphone-models.json`. Năm 2025 và 2026
  rỗng trong file gốc nên **không seed** — không tự bịa model.
- Landing đọc từ `/api/catalog/iphone-models`; **không hard-code model trong HTML**.
- Thêm model mới = INSERT vào bảng hoặc qua API admin (G06), **không phải sửa HTML**. Có test.
- **G06 đã xong phần còn lại:**
  - `POST /api/admin/iphone-models` — thêm model. Validate `model_code` theo slug
    `^[a-z0-9][a-z0-9-]{0,63}$`, `year` trong `2007..2100`, `extra="forbid"`.
  - `PATCH /api/admin/iphone-models/{model_code}` — sửa `display_name`, `active`, `sort_order`.
    **Không** cho sửa `model_code`/`year` (đổi mã là làm gãy dữ liệu cũ); gửi trường lạ → **422**.
  - Trùng `model_code` → **409** (kể cả khi hai admin thêm cùng lúc: ràng buộc UNIQUE ở DB thắng).
  - **Không tự bịa model**: hệ thống không suy model kế tiếp, không seed kèm. Test đo
    "thêm MỘT model thì bảng tăng ĐÚNG một dòng".
- **Bằng chứng "không phải sửa HTML" (ba phép đo độc lập):**
  1. Băm SHA-256 của **mọi file `.html`** trước và sau khi thêm model — giống nhau từng byte.
  2. `/api/catalog/iphone-models` (đúng thứ landing gọi) có model mới.
  3. **Chromium thật** nạp `/`, đọc `<option>` trong `#iphone_model` và thấy model mới
     (`tests_e2e/test_g04_g06_browser.py`).
- Model không có trong danh mục, hoặc `active = false`, bị API **từ chối** (`MODEL_NOT_IN_CATALOG`).

---

## 12. TRACKING

`src`, `ref`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `campaign`.

- Frontend: whitelist 7 tham số, chỉ nhận ký tự an toàn, lưu `sessionStorage` → điều hướng không mất nguồn.
- Server: kiểm lại bằng biểu thức `^[A-Za-z0-9._~-]{1,64}$` (**trùng khớp** với frontend). Giá trị
  có khoảng trắng, dấu `<`, dấu nháy, hay dài quá 64 ký tự bị **từ chối 422**.
- **Không đưa PII vào query string.**

5 dataLayer event bắt buộc: `vipphone_landing_view`, `vipphone_form_start`, `vipphone_lead_submit`,
`vipphone_gift_code_created`, `vipphone_gift_redeemed`.

> **Trạng thái thật:** mới có `window.dataLayer`. **CHƯA** nối GTM/GA4/Meta Pixel thật, **CHƯA** có
> consent banner riêng cho tracking. `TRACKING = DATA_LAYER_ONLY`.

---

## 13. BẢO MẬT

### 13.1 Đã xử lý ở G01/G02

| # | Việc | Trạng thái |
|---|---|---|
| S1 | Validation server-side, không tin client | **XONG** — Pydantic + `extra="forbid"`, từ chối `iphone_year`/`gift_status`/`lead_id` do client gửi |
| S3 | Ranh giới xác thực nhân viên | **CÓ** — `X-Staff-Key` / `Bearer`, so sánh `compare_digest`. **Fail CLOSED**: chưa cấu hình → **503** |
| S4 | Rate limit | **CÓ** — cửa sổ trượt theo IP, có test 429 + `Retry-After` |
| S5 | Audit trail | **XONG cho luồng hiện có** — `LEAD_CREATED`, `GIFT_CREATED`, `GIFT_STATUS_CHANGED`, `GIFT_REDEEMED`, ghi CÙNG transaction với thay đổi |
| S7 | Security header | **CÓ** — CSP nghiêm, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP; HSTS chỉ khi HTTPS |
| S8 | CSRF | Không dùng cookie/session; xác thực qua header nên **không bị CSRF cổ điển**. Ghi rõ để không tưởng là đã làm |
| S10 | Secret scanning | **CÓ** — gitleaks 8.30.1, quét toàn bộ lịch sử git |
| S11 | Whitelist giá trị tracking | **CÓ** |
| S12 | `redeemed_by` hard-code | **XONG** — actor suy từ khoá nhân viên, không hard-code |
| — | PII minimization | Che SĐT (`0912***678`), không trả UTM/công ty/BNI cho nhân viên, không lưu SĐT vào `sessionStorage` |
| — | SQL injection | Tham số hoá toàn bộ qua SQLAlchemy; có test chèn `'); DROP TABLE leads;--` và xác nhận lưu nguyên văn, bảng còn nguyên |
| — | XSS | Escape mọi nội dung người dùng; CSP `script-src 'self'`; **không** inline script/style trong HTML (CI chặn). Trang quản trị dựng DOM bằng `textContent`/`createTextNode`, **không** dùng `innerHTML` cho dữ liệu |
| S2 | Khu vực dữ liệu đầy đủ | **CÓ** (G05) — `/api/admin/*` có xác thực riêng, trả đủ trường. Màn nhân viên tại quầy vẫn che SĐT |
| S6 | **IDOR** | **CÓ test** (G05) — thiếu/sai khoá ⇒ 401 cho mọi route admin và **không** byte nào của lead lọt ra; lead có và lead không tồn tại trả **cùng** kết quả |
| — | **CSV formula injection** | **CÓ** (G05) — ô bắt đầu bằng `=`, `+`, `-`, `@`, TAB, CR bị thêm `'` ở đầu. Đo bằng 14 test + trình duyệt thật tải file |
| — | Trần dữ liệu ra | `page_size ≤ 200` (422 nếu vượt), CSV `≤ 5.000` dòng kèm header báo bị cắt |
| — | Ranh giới ghi danh mục | `POST`/`PATCH` model đều `require_staff`; test đo **số dòng trong bảng** không đổi khi thiếu khoá |

### 13.2 CÒN MỞ (ghi đúng, không tô hồng)

| # | Việc | Gate |
|---|---|---|
| — | Turnstile chỉ có **adapter**, chưa bật ở đâu (chưa có secret thật) | G08 / cần Owner |
| — | Rate limit **trong bộ nhớ tiến trình** → nhiều instance thì mỗi instance đếm riêng. Ghi rõ, **không** giả vờ đủ cho production nhiều instance | G08 |
| — | Chưa có `pip-audit` / dependency scan trong CI | G08 |
| — | **Thay đổi danh mục iPhone KHÔNG ghi audit** — bảng `audit_events` có CHECK constraint liệt kê 4 `event_type`; thêm loại mới cần migration. Chưa làm trong gate này | G08 |
| — | **Trang `admin-leads.html` được phục vụ công khai** (chỉ là vỏ, không chứa dữ liệu). Chặn ở tầng trang là chặn nhầm chỗ vì trình duyệt không gửi được header xác thực khi mở HTML | chấp nhận có ghi lý do |
| — | **CSV không có BOM** ⇒ Excel có thể hiển thị sai dấu tiếng Việt khi mở trực tiếp | G08 |
| — | **Bộ E2E chưa nối vào CI** (CI không có Chromium) ⇒ dễ bị bỏ quên | G10 |
| — | Chưa rà soát PII lọt vào log production | G08 |

---

## 14. TESTS

**280 test backend, tất cả PASS** — đo bằng `python -m pytest -q` trên **PostgreSQL 16 thật**.
Phạm vi: `tests/` (unit + integration). Trước gate này: **163** ⇒ **+117**.

**14 test E2E trình duyệt thật, tất cả PASS** — đo bằng `make test-e2e`
(`.venv/bin/python -m pytest -q tests_e2e`). Phạm vi: `tests_e2e/`, dựng uvicorn thật +
PostgreSQL `_test` thật + Chromium thật. **Bộ này KHÔNG chạy trong CI.**

Tổng: **294 test**, chia làm hai lệnh vì E2E cần Chromium.

| File | Nội dung |
|---|---|
| `tests/test_phone.py` | 30 ca chuẩn hoá SĐT, kể cả idempotent và "mọi cách viết ra một giá trị" |
| `tests/test_giftcodes.py` | định dạng, entropy, không tuần tự, tra cứu hoa/thường |
| `tests/test_health_and_headers.py` | `/api/health`, `/api/ready`, security header, CSP, shortlink |
| `tests/test_leads_api.py` | lead hợp lệ, SĐT sai, thiếu consent, trùng lặp, gift code duy nhất, đụng độ + thử lại, UTM, model, SQLi, rate limit |
| `tests/test_gifts_api.py` | xác thực, che PII, mã sai, **QR giải mã thật**, danh mục |
| `tests/test_redeem_api.py` | redeem thành công, idempotent, CANCELLED bị từ chối, phân quyền, **khoá hàng tất định**, đa luồng |
| `tests/test_migrations.py` | upgrade/downgrade trên **database tạm riêng**, seed, UNIQUE một phần, CHECK, `alembic check` |
| `tests/test_admin_leads_api.py` | **mới (G05)** — 54 ca: xác thực/IDOR, phân trang, trần `page_size`, mọi bộ lọc, chi tiết, CSV (chống injection, trần dòng, cùng bộ lọc) |
| `tests/test_admin_catalog_api.py` | **mới (G06)** — 51 ca: xác thực, validate slug/năm, trùng mã, PATCH, "thêm model không đổi byte HTML nào" |
| `tests/test_admin_pages.py` | **mới** — trang mới phục vụ được, CSP vẫn NGHIÊM, script chỉ từ chính origin |
| `tests_e2e/test_g04_g06_browser.py` | **mới** — 14 ca Chromium thật: nút quét QR ẩn/hiện theo năng lực trình duyệt, khoá chỉ ở `sessionStorage`, landing thấy model mới, trang quản trị không lỗi CSP |

Đối chiếu với 14 kịch bản bắt buộc của G09:

| # | Kịch bản | Trạng thái |
|---|---|---|
| 1 | valid lead | **PASS** |
| 2 | invalid phone | **PASS** |
| 3 | missing consent | **PASS** |
| 4 | duplicate submission | **PASS** |
| 5 | gift code uniqueness | **PASS** |
| 6 | gift lookup | **PASS** |
| 7 | redeem success | **PASS** |
| 8 | redeem second time | **PASS** (idempotent) |
| 9 | concurrent redeem | **PASS** (khoá hàng, test tất định) |
| 10 | invalid gift code | **PASS** |
| 11 | UTM capture | **PASS** |
| 12 | model validation | **PASS** |
| 13 | database migration | **PASS** |
| 14 | health endpoint | **PASS** |

---

## 15. CI

Workflow: `.github/workflows/ci.yml`. 3 job:

| Job | Nội dung |
|---|---|
| `Secret scan (gitleaks)` | gitleaks 8.30.1, `fetch-depth: 0`, quét toàn bộ lịch sử |
| `Validate static frontend` | file bắt buộc (đã thêm `admin-leads.html`, `qr-scan.js`, `admin-leads.js`, `app/routers/admin.py`), JSON hợp lệ, `node --check`, chốt chặn QR giả / QR phải từ server / **khoá nhân viên chỉ ở `sessionStorage`** (phủ cả `redeem.js` và `admin-leads.js`, có đối chứng dương) / HTML không inline (phủ thêm `admin-leads.html`) |
| `Backend (lint, migration, tests)` | PostgreSQL 16 service container, ruff (đã thêm `tests_e2e`), `alembic upgrade head` + `alembic check`, unit test, integration test, full suite |

Trạng thái CI của G02: **cập nhật ngay sau khi PR được tạo** (xem PR tương ứng).

Chốt an toàn: `tests/conftest.py` **từ chối chạy** nếu `TEST_DATABASE_URL` không trỏ tới database
có tên kết thúc bằng `_test` — tránh xoá nhầm database thật.

---

## 16. STAGING / PRODUCTION

| Mục | Trạng thái |
|---|---|
| `.env.example` | **CÓ** — không chứa secret thật |
| `/api/health` | **CÓ** |
| `/api/ready` | **CÓ** — nói thẳng phần chưa cấu hình |
| `docs/deployment.md` | **CHƯA CÓ** → G11 |
| Hạ tầng staging | **CHƯA CÓ** → `BLOCKED_EXTERNAL_INFRA` cho tới khi Owner cung cấp |
| STAGING | **NOT DEPLOYED** |
| PRODUCTION | **NOT DEPLOYED** |

**Không có câu nào trong tài liệu này được phép đọc thành "secure production".** Chưa có
hạ tầng, chưa có HTTPS thật, chưa có secret thật, chưa có giám sát, chưa có diễn tập khôi phục.
Gate G04/G05/G06 làm phần mềm **đúng hơn**, không làm nó **đã triển khai được**.

---

## 17. BÀI HỌC ĐO LƯỜNG (ghi lại để không lặp)

Trong phiên này, **năm lần** thứ dùng để kiểm chứng tự nó không trung thực. Ghi lại vì đây
đúng là loại lỗi khó thấy nhất — nó không báo lỗi, nó chỉ báo sai.

| # | Chuyện gì | Xử lý |
|---|---|---|
| 1 | Bước secret scan baseline `grep` khớp **chính nó** → CI đỏ 2/2 run | Thay bằng gitleaks; siết mẫu grep; ghép mẫu từ nhiều mảnh chuỗi |
| 2 | Viết lại §1.1, bản nháp **chép nguyên văn** mẫu regex → chốt chặn mới báo đỏ trên chính tài liệu | Sửa tài liệu, **không** nới chốt chặn |
| 3 | Test E2E báo `gift_code_created` không phát ra — thật ra là **lỗi phép đo**: `dataLayer` thuộc từng trang, đọc sau khi điều hướng thì mất event của trang trước | Ghi bền event vào `sessionStorage` rồi đo lại. **Không** sửa code cho vừa test |
| 4 | Bộ giải mã QR **OpenCV** giải mã được hầu hết gift code nhưng **thất bại** với `VIP-26-AAAAAA` và `VIP-26-BBBBBB`; zxing-cpp giải mã bình thường | Đổi sang zxing-cpp. Nếu không phát hiện, test QR sẽ **pass giả** ở hầu hết trường hợp và **fail giả** ở một số trường hợp — cả hai đều làm hỏng niềm tin vào kết quả |
| 5 | 6 test trong `test_leads_api.py` báo hỏng, nhưng chạy riêng thì **pass hết** | Nguyên nhân: một test trước đó **tắt một model trong danh mục**, fixture dọn dẹp không dựng lại danh mục → các test sau hỏng vì lý do không liên quan tới chúng. Sửa fixture để dựng lại **cả** danh mục, dùng chung hàm seed với migration |
| 6 | **7 test migration pass ở máy nhưng FAIL trên CI**: `password authentication failed for user "vipphone"` | `str(URL)` của SQLAlchemy **che password thành `***`**. Máy local đăng nhập kiểu `trust` nên URL **không có password** → không thấy gì; CI dùng service container **có password** → engine kết nối bằng `***`. Sửa thành `render_as_string(hide_password=False)`. **Đã tái hiện lỗi tại máy** bằng cách bật `scram-sha-256` cho PostgreSQL cục bộ rồi chạy lại: **7 failed** với mã cũ, **7 passed** với bản vá. Đây là lý do **phải có CI chạy trên PostgreSQL thật có password** — chạy máy không bắt được |
| 7 | gitleaks báo 1 leak: `test-staff-key-0123456789abcdef` trong `tests/conftest.py` | Không phải secret thật, nhưng **trông giống** credential nên làm nhiễu đúng công cụ dùng để bắt secret thật. Đổi thành giá trị độ phức tạp thấp. Chuỗi cũ vẫn nằm trong **lịch sử commit chưa merge**, nên xử lý bằng cách **viết lại commit** chứ **không** thêm allowlist — thêm allowlist là làm yếu công cụ kiểm chứng |

| 8 | Test đồng thời `test_concurrent_redeem_only_one_wins` **PASS 5/5 lần dù ĐÃ BỎ `with_for_update()`** | Test không phân biệt được. Nguyên nhân đo được: 8 luồng mất ~20ms bắt tay kết nối (scram) nên các `SELECT` bị so le, cuộc đua **không xảy ra** (đo trực tiếp: 1 lần ghi thắng). Bản vá đầu tiên (kiểm "service có ném lỗi khoá không") **cũng không phân biệt được** — bỏ khoá thì service chờ ở câu `UPDATE`, vẫn ném cùng loại lỗi. Bản vá thật: đọc `pg_stat_activity` để xem backend đang chờ **Ở CÂU NÀO** — phải là `SELECT … FOR UPDATE`. **Đã kiểm bằng đối chứng âm**: bỏ khoá → 2 test FAIL; khôi phục → 2 test PASS |

| 9 | Test "nút quét QR phải ẨN khi trình duyệt không hỗ trợ" **PASS giả** ở lần chạy đầu: test báo FAIL, nhưng nguyên nhân là **sản phẩm sai**, không phải test sai. CSS `.secondary-btn{display:inline-block}` **đè** lên `[hidden]` của stylesheet gốc, nên nút "đã ẩn" theo HTML vẫn **HIỆN**. Đọc mã thấy `hidden`, grep thấy `hidden` — chỉ Chromium thật nói ra sự thật | Thêm `[hidden]{display:none!important}`. Ghi lại thành đối chứng âm NC13: bỏ quy tắc đó → test FAIL |
| 10 | **Hai test PASS vì lý do KHÁC với điều mình tưởng.** (a) "PATCH không cho sửa `model_code`" đạt nhờ validator *"thiếu trường hợp lệ"*, **không** nhờ `extra="forbid"` — đổi sang `extra="ignore"` test vẫn PASS. (b) "SĐT không được thành wildcard" đạt nhờ lớp *chuẩn hoá chữ số*, **không** nhờ `escape_like` — bỏ `escape_like` test vẫn PASS | Sửa (a): parametrize thêm ca **trộn** trường hợp lệ + trường lạ → `extra="ignore"` làm 3/4 ca FAIL. Đo (b) bằng **hai** đối chứng: bỏ lớp chuẩn hoá mà giữ escape → vẫn PASS (escape đủ chặn); bỏ **cả hai** → FAIL. Không xoá `escape_like` vì nó là lớp phòng thủ thật, nhưng ghi rõ nó chỉ quan sát được ở ca thứ hai |
| 11 | `page.goto(..., wait_until="networkidle")` **không bao giờ đạt** trên `/redeem.html?code=…`: Playwright treo tới hết 30 s dù trang đã render xong và API đã trả lời (thấy `RESPONSE 401` trong sự kiện, nhưng không có `requestfinished`). Đo thêm: cùng lỗi với mã hợp lệ (200) và với `fetch` gọi từ `page.evaluate` — kể cả `fetch` danh mục vốn vẫn idles được khi chạy lúc tải trang. **Nguyên nhân gốc chưa chốt được** | **Không** kết luận gì về sản phẩm. Bỏ hẳn `networkidle`, chuyển sang `wait_until="load"` + chờ **điều kiện DOM cụ thể**. Điều kiện chờ không giải thích được là điều kiện chờ không được tin |
| 12 | Test đầu tiên của G06 vừa liệt kê `iphone--` vào danh sách slug **SAI**, vừa liệt kê nó vào danh sách slug **ĐÚNG** | Đọc lại đề bài: regex `^[a-z0-9][a-z0-9-]{0,63}$` **cho phép** gạch ngang cuối. Bỏ khỏi danh sách sai. Bài học: danh sách ca thử cũng là một phép đo, và nó cũng có thể tự mâu thuẫn |

**Nguyên tắc rút ra (bổ sung sau ca 8):** một test **PASS** không có nghĩa là nó
**kiểm được điều mình tưởng**. Muốn biết một test có thật sự phân biệt được không, phải
**phá thứ nó định bảo vệ rồi xem nó có FAIL không** — gọi là đối chứng âm. Test nào không
FAIL khi phá thì test đó **chưa kiểm gì cả**, dù nó xanh.

Khi một chốt chặn báo động, câu hỏi đầu tiên phải là *"chốt chặn sai hay dữ liệu sai?"* —
và câu trả lời phải bằng **một phép đo**, không bằng cảm giác. Bốn lần đầu là **công cụ sai**;
lần 5 và 6 là **dữ liệu/thiết lập sai** (chỉ lộ trên CI); lần 7 là **giá trị thử nghiệm gây nhiễu**;
lần 8 là **phép đo không phân biệt được**. Sửa đúng chỗ, không sửa cho vừa mắt.

**Ca 9–12 (gate G04+G05+G06) là loại khó nhất:** ở ca 10, *test xanh, sản phẩm đúng, mà kết luận
vẫn sai* — vì test đạt nhờ một cơ chế khác với cơ chế mình tưởng nó đang kiểm. Cách duy nhất
phát hiện là **đối chứng âm**, và ở ca 10 đối chứng âm đầu tiên **không FAIL** nên phải đổi
chính phép đo.

---

## 18. LUẬT KHÔNG ĐƯỢC VI PHẠM

- **KHÔNG** sửa trực tiếp `main`.
- **KHÔNG** sửa trực tiếp production/VPS.
- **KHÔNG** force push `main`/`develop`.
- **KHÔNG** bỏ qua CI.
- **KHÔNG** commit secret / credential.
- **KHÔNG** tự deploy production khi chưa có release gate của Owner.
- **KHÔNG** sửa code đang LOCKED nếu không có CR mới.
- **PRODUCTION DEPLOY = FORBIDDEN** trong phiên này.

### 18.1 Luật drift trước mọi merge

Đo **expected develop SHA** · **actual develop SHA** · **PR HEAD** · **merge-base**.
Nếu `develop` lệch khỏi giá trị mong đợi → **STOP MERGE**, reconcile trước. Không merge mù.

---

## 19. CÁCH ĐO LẠI (evidence commands)

```bash
# Baseline / GitHub
gh repo view thanhbn123/vipphone --json defaultBranchRef,visibility
git rev-parse origin/main origin/develop && git merge-base origin/main origin/develop
gh issue list --repo thanhbn123/vipphone --state all
gh pr list    --repo thanhbn123/vipphone --state all
gh run list   --repo thanhbn123/vipphone --limit 20

# Chất lượng
make lint                     # ruff check + format --check (app, tests, tests_e2e, migrations)
make test                     # pytest trên PostgreSQL thật
make test-e2e                 # E2E Chromium thật + máy chủ thật + PostgreSQL _test
make migrate-check            # alembic upgrade head + alembic check
make secret-scan              # gitleaks toàn bộ lịch sử git
```

```bash
# Khu vực quản trị (thay <KEY> bằng khoá trong STAFF_API_KEYS)
curl -s -H "X-Staff-Key: <KEY>" 'localhost:8000/api/admin/leads?phone=0912&page_size=25'
curl -s -H "X-Staff-Key: <KEY>" 'localhost:8000/api/admin/leads.csv?source=bni' -o leads.csv
curl -s -H "X-Staff-Key: <KEY>" 'localhost:8000/api/admin/leads/<lead_id>'
curl -s -H "X-Staff-Key: <KEY>" -X POST localhost:8000/api/admin/iphone-models \
     -H 'Content-Type: application/json' \
     -d '{"model_code":"iphone-17-pro","display_name":"iPhone 17 Pro","year":2027,"sort_order":-5}'

# Chốt an toàn: không có khoá ⇒ 401; chưa cấu hình ⇒ 503
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/admin/leads
```

---

## 20. ĐỐI CHỨNG ÂM (gate G04+G05+G06) — đo, không suy đoán

**Luật:** với **mọi** test an ninh, phải tạm **phá** đúng thứ nó định bảo vệ, chạy lại, và
chứng minh nó **FAIL**. Rồi khôi phục và chứng minh nó **PASS**. Test nào không FAIL khi phá
thì **chưa kiểm gì cả**, dù nó xanh.

Cách chạy: script vá từng chỗ trong mã nguồn, chạy đúng test liên quan, **khôi phục nguyên
trạng** rồi chạy lại. Không dùng `git checkout` để khôi phục (các file đang có thay đổi chưa
commit); sao lưu từng file ra ngoài rồi ghi đè lại, và sau cùng `diff` để xác nhận không sót.
**16/16 ca đạt.**

| Kết luận | Ca phá | File bị vá | Khi ĐÃ PHÁ | Sau khi KHÔI PHỤC |
|---|---|---|---|---|
| **ĐẠT** | NC1 — bỏ xác thực ở route danh sách lead | `app/routers/admin.py` | 1 failed / 3 passed | 0 failed / 4 passed |
| **ĐẠT** | NC2 — bỏ chống CSV formula injection | `app/services/admin_leads.py` | 14 failed / 0 passed | 0 failed / 14 passed |
| **ĐẠT** | NC3 — bỏ trần page_size | `app/routers/admin.py` | 2 failed / 2 passed | 0 failed / 4 passed |
| **ĐẠT** | NC4 — nới regex slug model_code | `app/schemas.py` | 8 failed / 1 passed | 0 failed / 9 passed |
| **ĐẠT** | NC5 — bỏ chặn year < 2007 | `app/schemas.py` | 5 failed / 0 passed | 0 failed / 5 passed |
| **ĐẠT** | NC6 — bỏ trần số dòng CSV | `app/routers/admin.py` | 1 failed / 0 passed | 0 failed / 1 passed |
| **ĐẠT** | NC7 — CSV bỏ qua bộ lọc (khác danh sách) | `app/routers/admin.py` | 1 failed / 0 passed | 0 failed / 1 passed |
| **ĐẠT** | NC8a — bỏ lớp 1 (chuẩn hoá chữ số), GIỮ escape LIKE | `app/services/admin_leads.py` | 0 failed / 1 passed | 0 failed / 1 passed |
| **ĐẠT** | NC8b — bỏ CẢ HAI lớp (chuẩn hoá chữ số + escape LIKE) | `app/services/admin_leads.py` | 1 failed / 0 passed | 0 failed / 1 passed |
| **ĐẠT** | NC9 — bộ lọc SĐT rỗng lặng lẽ thành 'không lọc gì' | `app/services/admin_leads.py` | 1 failed / 0 passed | 0 failed / 1 passed |
| **ĐẠT** | NC10 — nút quét QR hiện vô điều kiện | `assets/js/redeem.js` | 1 failed / 0 passed | 0 failed / 1 passed |
| **ĐẠT** | NC11 — ghi khoá nhân viên vào localStorage | `assets/js/redeem.js` | 1 failed / 0 passed | 0 failed / 1 passed |
| **ĐẠT** | NC12 — landing dùng danh sách cứng thay vì gọi API danh mục | `assets/js/app.js` | 1 failed / 0 passed | 0 failed / 1 passed |
| **ĐẠT** | NC13 — bỏ quy tắc [hidden] (đúng lỗi CSS đã bắt được) | `assets/css/styles.css` | 1 failed / 0 passed | 0 failed / 1 passed |
| **ĐẠT** | NC14 — require_staff fail OPEN khi chưa cấu hình | `app/security.py` | 1 failed / 0 passed | 0 failed / 1 passed |
| **ĐẠT** | NC15 — PATCH cho phép gửi trường lạ (model_code/year) | `app/schemas.py` | 3 failed / 1 passed | 0 failed / 4 passed |

Đọc bảng này cho đúng:

- **NC8a là ca CỐ Ý để test vẫn PASS** khi phá. Nó không phải ca hỏng: nó chứng minh lớp
  phòng thủ thứ hai (`escape_like`) một mình đã đủ chặn. Ca NC8b (bỏ cả hai lớp) mới là ca
  chứng minh test **sống**.
- **NC13 là ca đáng chú ý nhất**: nó phá đúng quy tắc CSS mà lỗi thật đã dính (ca 9 ở §17).
  Nghĩa là test E2E bắt được **đúng** lỗi cũ, không phải một lỗi tưởng tượng.
- **NC10, NC11, NC12, NC13 chạy trên Chromium thật** (`tests_e2e/`), không phải bằng grep.
- Hai ca đầu tiên của NC8/NC15 **không FAIL**; xem §17 ca 10 để biết đã sửa phép đo thế nào.

**Phạm vi đã đo (nói đúng phạm vi, không suy rộng):** 16 đối chứng âm này phủ các test an ninh
**mới của gate G04/G05/G06** — xác thực/IDOR route admin, chống CSV formula injection, trần
`page_size`, trần dòng CSV, "CSV cùng bộ lọc", validate slug/năm của model, `extra="forbid"`
khi PATCH, escape LIKE, fail-closed khi chưa cấu hình, ẩn nút quét QR, khoá chỉ ở sessionStorage,
landing đọc danh mục từ API. **Nằm NGOÀI phạm vi:** các test an ninh của G01–G03 (đã có đối
chứng âm riêng ở gate đó) và các test không mang tính an ninh (validate định dạng, sắp xếp,
phân trang thường). Không có nghĩa "toàn bộ test của dự án đã được đối chứng âm".
