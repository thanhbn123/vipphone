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
| G08 | Security pass | **DONE** | [#12](https://github.com/thanhbn123/vipphone/pull/12) | **PASS** | `381abefdcb304376a177b2153daac4044ca7fd6e` |
| G09 | Tests đầy đủ | **DONE** — 297 backend + 30 E2E (Chromium thật) | [#14](https://github.com/thanhbn123/vipphone/pull/14) | **PASS** (5/5 job) | `d4648f46cd801cf323b715a3eba334ff3570ca4e` |
| G10 | CI đầy đủ | **DONE** — 5 job, gồm E2E chạy thật và quét phụ thuộc | [#14](https://github.com/thanhbn123/vipphone/pull/14) | **PASS** (5/5 job) | `d4648f46cd801cf323b715a3eba334ff3570ca4e` |
| G11 | Staging readiness | **DONE (tài liệu)** — `docs/deployment.md`; **hạ tầng staging = BLOCKED_EXTERNAL_INFRA** | [#16](https://github.com/thanhbn123/vipphone/pull/16) | **PASS** (5/5 job) | `93e6aae11f6f17b860b083abbba7c7832bb2ae67` |
| G12 | Owner acceptance pack | **DONE** — `docs/OWNER_ACCEPTANCE.md` | [#16](https://github.com/thanhbn123/vipphone/pull/16) | **PASS** (5/5 job) | `93e6aae11f6f17b860b083abbba7c7832bb2ae67` |

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
| — | **Bộ E2E chưa nối vào CI** (CI không có Chromium) ⇒ dễ bị bỏ quên | G10 | CI đầy đủ | **DONE** — 5 job, gồm E2E chạy thật và quét phụ thuộc | [#14](https://github.com/thanhbn123/vipphone/pull/14) | **PASS** (5/5 job) | `d4648f46cd801cf323b715a3eba334ff3570ca4e` |
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

---

## 21. G08 — SECURITY PASS (5 lỗ hổng vá, 4 đối chứng âm)

Rà soát trên `develop` = `92a4952` tìm được **8 phát hiện**; gate này vá 5. Ba phát hiện
còn lại vẫn **MỞ** và được ghi ở §13.2.

| # | Lỗ hổng | Mức | Bản vá |
|---|---|---|---|
| F1 | Trần body kiểm **SAU khi đã đọc hết** vào RAM ⇒ trần 8 KB không bảo vệ được gì trước payload lớn | trung-cao | `app/limits.py`: kiểm `Content-Length` **trước khi chạm body**; body chunked đọc theo khối, bỏ ngay khi vượt trần |
| F2 | `/api/ready` công khai lộ `env`, `version`, `migration_head`, và **staff auth / Turnstile có cấu hình hay không** — tức là nói cho người lạ biết bot protection đang TẮT | trung | Công khai chỉ còn `{"status"}`; chi tiết chỉ khi có khoá nhân viên hợp lệ, hoặc bật tường minh `EXPOSE_READINESS_DETAILS` |
| F3 | Cấu hình CORS là **MÃ CHẾT**: `cors_origin_list` có trong config nhưng **không middleware nào dùng**. Đọc như đã làm mà thực ra chưa làm — tệ hơn cả không có | trung | Gỡ hẳn + ghi lý do tại chỗ; có test khẳng định **không** rò header CORS cho origin lạ |
| F4 | Thiếu `TrustedHostMiddleware` | trung (khi có proxy) | Thêm `ALLOWED_HOSTS`; ở production mà rỗng thì **cảnh báo lúc khởi động** và readiness báo `NOT_CONFIGURED` — không im lặng |
| F5 | `request_id` khai mà **không ai truyền**; không có mã tương quan trong log/response | thấp | Middleware sinh `X-Request-ID`, lưu vào `request.state` |

### 21.1 Đối chứng âm — đo LẠI trên bản đã gộp với G04-G06

Bản vá được viết trên `92a4952`, rồi áp lên `18e4a6e` (sau G04-G06). **Phép đo cũ không
được tin sau khi rebase** — nên 4 đối chứng âm đã chạy lại trên bản đã gộp:

| Phá gì | Kết quả | Khôi phục |
|---|---|---|
| `read_limited_body` → đọc trước, kiểm sau | **1 failed** | 1 passed |
| `/api/ready` → luôn trả chi tiết | **1 failed** | 1 passed |
| Bỏ `TrustedHostMiddleware` | **1 failed** | 1 passed |
| Gắn `CORSMiddleware(allow_origins=["*"])` | **1 failed** | 1 passed |

**Phạm vi đã đo:** 4 đối chứng âm này phủ đúng 4 bản vá của G08. **Nằm ngoài phạm vi:**
các test an ninh khác của dự án (đã có đối chứng âm riêng ở gate của chúng). Không có
nghĩa "toàn bộ test an ninh đã được đối chứng âm".

### 21.2 Đổi hợp đồng — nói rõ

`GET /api/ready` **đổi hợp đồng**: trước đây trả hết cho công khai, nay công khai chỉ thấy
`status`. Hai test cũ đã được cập nhật theo hợp đồng mới. Ai đang dùng `/api/ready` để lấy
chi tiết thì phải gửi kèm khoá nhân viên.

### 21.3 Còn MỞ sau G08 (không được coi là đã xong)

- **Turnstile/reCAPTCHA**: mới có adapter, **chưa có khoá thật** ⇒ bot protection đang **TẮT**
- **Rate limit trong bộ nhớ tiến trình**: `--workers N` ⇒ giới hạn thực tế × N. Cần Redis nếu scale ngang
- **Chưa quét lỗ hổng phụ thuộc** trong CI (`pip-audit`) → G10
- **Chưa rà PII lọt vào log production**
- **`main` chưa bật branch protection** → cần Owner

---

## 22. KỶ LUẬT TÀI NGUYÊN DÙNG CHUNG (hai sự cố thật trong phiên này)

Bài học §20 nói về *phép đo*. Mục này nói về **tài nguyên**: làn không chỉ là **thư mục**,
mà còn là **database, cổng, tiến trình**. Hai sự cố đã xảy ra thật, cả hai đều ghi ra
thay vì giấu.

### 22.1 Hai phiên cùng chạy test trên MỘT database → deadlock

Lúc gate G04+G05+G06 đang chạy test, controller cũng chạy `pytest tests` với
`TEST_DATABASE_URL=…/vipphone_test` — **cùng một database**. Kết quả đo được:

```
psycopg.errors.DeadlockDetected: deadlock detected
DETAIL: Process 75050 waits for AccessExclusiveLock on relation …; blocked by process 75051.
        Process 75051 waits for AccessShareLock on relation …; blocked by process 75050.
[SQL: TRUNCATE TABLE iphone_models RESTART IDENTITY CASCADE]
178 passed, 1 error
```

Hai tiến trình cùng `TRUNCATE` bảng `iphone_models` ⇒ khoá chéo nhau. **Không phải lỗi sản
phẩm** — là lỗi vận hành của phiên. Hệ quả có thể có: phép đo của gate bị nhiễu một lượt.

**Luật rút ra:**
- Mỗi phiên kiểm chứng dùng **database RIÊNG**, tên mang dấu vết phiên
  (`vipphone_g08_test`, `vipphone_g08_e2e_test`).
- **Trước khi chạy test**, kiểm `pg_stat_activity` xem database đó có ai đang dùng.
- Không bao giờ trỏ `TEST_DATABASE_URL` vào database mà phiên khác có thể đang dùng.

### 22.2 Tiến trình nền dừng lại — và ghi rõ AI đã dừng

Gate báo một điều bất thường: tiến trình uvicorn nền cũ (**PID 64410**, cổng 8000) mà nó
từng thấy qua `lsof`/`ps` thì nay không còn chạy, và nó xác nhận **chưa từng** chạy
`kill`/`pkill`/`killall`. Câu hỏi đó có đáp án, và câu trả lời là **controller**.

Đó là uvicorn do controller khởi động lúc 18:56 cho việc kiểm chứng E2E của G03, rồi
để chạy nền quên tắt. Khi phát hiện, controller đã:
1. `ps -p 64408,64410 -o pid,ppid,lstart,command` để **nhìn tận mắt** hai tiến trình,
2. `lsof -nP -iTCP:8000 -sTCP:LISTEN` để xác nhận ai giữ cổng 8000,
3. `kill 64410` — **theo đúng PID**, không theo mẫu tên,
4. kiểm lại: cổng 8000 đã nhả, và các tiến trình python còn lại là của gate (PID khác),
   **không bị đụng tới**.

**Luật rút ra:** dừng tiến trình nền thì **ghi ra** (ai dừng, PID nào, lúc nào). Một tiến
trình biến mất mà không ai nhận là một câu hỏi chẩn đoán tốn thời gian cho phiên sau —
đúng ca 16:35:39 mà `CLAUDE.md` §16.7 đã ghi.

---

## 23. G09+G10 — TESTS + CI (ba lỗ hổng CI đã vá)

### 23.1 Ba lỗ hổng CI, đo được trước khi vá

| # | Lỗ hổng | Bằng chứng |
|---|---|---|
| 1 | CI **LINT** `tests_e2e` nhưng **KHÔNG CHẠY** nó | `pytest.ini` đặt `testpaths = tests`; cả ba lệnh pytest đều nằm trong phạm vi đó ⇒ **bộ E2E hỏng vẫn qua CI** |
| 2 | Không quét lỗ hổng phụ thuộc | `grep -n pip-audit ci.yml` → không có |
| 3 | `pytest.ini` thiếu marker `e2e` mà `--strict-markers` đang BẬT | dùng `pytest.mark.e2e` là **lỗi thu thập** ngay |

Lỗ hổng 1 đúng dạng bị cấm: **báo PASS trong khi test không chạy**. Một bộ test chỉ được
*lint* thì không bao giờ có thể FAIL.

**Vá:** thêm marker `e2e`; thêm job `e2e` (PostgreSQL 16 service container + Chromium thật,
upload trace khi hỏng) và job `dependency-scan` (`pip-audit --strict` cho cả hai file
requirements). CI nay có **5 job**.

### 23.2 Gộp hai bộ E2E — BỔ SUNG, không trùng

| Bộ | Nội dung | Số test |
|---|---|---|
| Của gate G04-G06 | danh mục → landing vẽ `<option>`, ẩn nút quét QR khi không hỗ trợ, khoá nhân viên không lưu lâu dài | 14 |
| Của controller | funnel: landing → lead → chuẩn hoá SĐT → QR giải mã → redeem → idempotent → RBAC → **mobile** | 16 |

**Cách gộp: chỉ THÊM, không SỬA.** Khối bổ sung nằm ở **cuối** `tests_e2e/conftest.py`
(`server`, `funnel_page`, `mobile_context`, `recorded_events`); 203 dòng đầu của gate
**không đổi một ký tự** (đã `diff` xác nhận). Trong module test funnel có bí danh cục bộ:

```python
@pytest.fixture
def page(funnel_page):
    return funnel_page
```

Pytest cho fixture khai trong module **đè** fixture cùng tên ở `conftest.py` **chỉ cho module
đó** — nên bộ funnel dùng bộ ghi event bền, còn test của gate vẫn dùng fixture gốc.

### 23.3 Vì sao funnel cần bộ ghi event RIÊNG

`window.dataLayer` là biến của **từng trang**; đọc sau khi điều hướng sẽ MẤT event của trang
trước — lỗi đo đã dính thật (§17 ca 3). Bộ ghi ghi vào `sessionStorage` để event sống sót.

### 23.4 Vá kèm: CSV thiếu BOM UTF-8

Gate G05 đã tự ghi nhận *"CSV không có BOM ⇒ Excel có thể hiển thị sai dấu tiếng Việt"*.
Đây là lỗi người dùng cuối gặp **ngay lần mở file đầu tiên**, nên vá kèm: `_csv_response`
nay thêm 3 byte `EF BB BF` ở đầu.

**Đổi hợp đồng:** file CSV nay **có BOM**. Test `test_csv_has_stable_header` được cập nhật
để bỏ BOM trước khi so (đúng cách một trình đọc CSV chuẩn xử lý), và thêm test mới
`test_csv_starts_with_utf8_bom_for_excel` khẳng định byte đầu là BOM **và** phần sau BOM vẫn
giữ đúng dấu tiếng Việt.

### 23.5 Đối chứng âm

| Phá gì | Kết quả | Khôi phục |
|---|---|---|
| Bỏ BOM khỏi CSV | **1 failed** | 1 passed |
| Tiêm PII vào payload QR | **1 failed** (đúng test PII) | 1 passed |

### 23.6 Job `dependency-scan` bắt được một lỗ hổng THẬT ngay lần chạy đầu

Đây là bằng chứng job mới có tác dụng, không phải trang trí:

```
Found 2 known vulnerabilities in 1 package
Name   Version ID              Fix Versions
pytest 8.4.2   PYSEC-2026-1845 9.0.3
  pytest through 9.0.2 on UNIX relies on directories with the
  /tmp/pytest-of-{user} name pattern, which allows local users to cause a
  denial of service or possibly gain privileges.
```

Phạm vi: **phụ thuộc DEV** (`pytest`), không phải đường chạy production —
`pip-audit -r requirements.txt` (runtime) **sạch** cả trước và sau.

**Đã xử lý, không tắt job:** nâng lên `pytest>=9.0.3,<10` (thực tế cài 9.1.1),
`pytest-cov~=6.3`. Rồi **chạy lại toàn bộ trên pytest 9**: 297 backend + 30 E2E
PASS, và cả hai cách chạy theo marker như CI (`-m "not integration"` → 57 passed;
`-m integration` → 240 passed). `pip-audit --strict` cho **cả hai** file
requirements → `No known vulnerabilities found`.

Ghi rõ lý do pin ngay trong `requirements-dev.txt` để không ai hạ về lại.

---

## 24. G11+G12 — STAGING READINESS + GÓI NGHIỆM THU

Hai tệp tài liệu, cùng nguồn dữ kiện, gộp một PR (không phải mega-PR: 2 tệp + cập nhật file này).

### 24.1 `docs/deployment.md`

Kiến trúc (1 tiến trình uvicorn + PostgreSQL 16) · yêu cầu phiên bản · bảng **22 trường cấu
hình** khớp `Settings.model_fields` (đã kiểm bằng script, không bằng mắt) · migration + rollback ·
systemd/nginx mẫu · health/ready · quy trình phát hành · **CI chạy 5 job gì** · và **danh sách
việc còn thiếu trước production**.

Hai điểm cố ý nhấn:
- `--workers N` làm rate limit **nhân lên N lần** (bộ đếm trong tiến trình). Ghi rõ, **không**
  tuyên bố "đã có rate limit" mà bỏ qua phạm vi.
- Ở production mà `ALLOWED_HOSTS` rỗng thì máy chủ **ghi cảnh báo** và readiness báo
  `NOT_CONFIGURED` — **cố ý ồn ào** chứ không im lặng.

### 24.2 `docs/OWNER_ACCEPTANCE.md`

Checklist **17 mục**, mỗi mục `PASS` / `FAIL` / `BLOCKED` kèm **lệnh đã chạy** hoặc **số đo**.
Có mục **"Bảng này KHÔNG nói gì"** và mục **"Việc cần Owner quyết"**.

**Đã kiểm bằng script:** 49 tên test được trích dẫn trong tài liệu **đều tồn tại thật** trong
`tests/` và `tests_e2e/`. Trích một test không tồn tại là bằng chứng giả, nên bước này không
được bỏ.

### 24.3 Trạng thái cuối

| Mục | Giá trị |
|---|---|
| `main` | `7d6162cf31eb96ea27879be3a4671812a9cd7e01` — **KHÔNG ĐỔI suốt phiên** |
| STAGING | **NOT DEPLOYED** |
| PRODUCTION | **NOT DEPLOYED** |
| Test | **297** backend + **30** E2E, tất cả PASS |
| CI | **5 job**, xanh trên cả ba PR đã merge |
| Đối chứng âm | **24 ca** đã đo (16 + 4 + 2 + 2 tất định), phạm vi ghi rõ |

---

## 25. SR-1 — HỢP ĐỒNG CẤU HÌNH STAGING + QUẢN TRỊ PII

Gate đầu của phiên **STAGING READINESS** (sau khi chuỗi G01–G12 đã xong).

### 25.1 Tệp mới

| Tệp | Nội dung |
|---|---|
| `.env.staging.example` | Mẫu biến cho staging, không có secret thật |
| `docs/staging.md` | Hợp đồng cấu hình: phân loại **REQUIRED/OPTIONAL · SECRET/PUBLIC · BUILD-TIME/RUN-TIME** cho **19 biến**, kèm "mã đọc biến này chưa" |
| `docs/pii-data-map.md` | Bản đồ PII: từng trường, vì sao thu, ai đọc, dùng làm gì |
| `docs/decisions/PII_RETENTION_OPTIONS.md` | 3 phương án trung lập, **không chọn hộ Owner** |
| `docs/OWNER_DECISIONS_REQUIRED.md` | D-001…D-004 |
| `scripts/enable_branch_protection.sh` | In lệnh cho Owner; mặc định **chỉ in**, cần `--apply` mới ghi |

### 25.2 Ba phát hiện khi soạn hợp đồng

1. **Không có `SECRET_KEY`/session signing secret, và không cần.** Stack không dùng cookie/phiên —
   xác thực nhân viên là khoá API qua header, so bằng `compare_digest`. Ghi rõ "không áp dụng" thay
   vì bịa ra một biến cho đủ danh sách.
2. **Không có biến BUILD-TIME nào.** Frontend không có bước build (ADR-0001 §3.2) ⇒ toàn bộ cấu hình
   là RUN-TIME. Đây là hệ quả của thiết kế, không phải thiếu sót.
3. **Bẫy Turnstile:** `TURNSTILE_SITE_KEY` chưa được mã đọc và frontend chưa có widget ⇒ bật
   `TURNSTILE_REQUIRED=true` **hôm nay sẽ chặn mọi lead**. Đã ghi cảnh báo; đường đi đầy đủ thuộc gate sau.

### 25.3 `.gitignore` suýt nuốt mất tệp mẫu

`.gitignore` có `.env.*` với đúng một ngoại lệ `!.env.example` ⇒ `.env.staging.example` **bị bỏ qua**.
Đã thêm ngoại lệ. **Bài học đo lường:** `git check-ignore -v` in ra dòng phủ định cuối cùng kể cả khi
tệp **KHÔNG** bị bỏ qua — nhìn nó mà kết luận là sai. Phép thử đáng tin là `git add -n <tệp>`.

### 25.4 Branch protection — đo, không giả PASS

```
main    : "Branch not protected" (404)
develop : "Branch not protected" (404)
rulesets: []
```

Token phiên này **có `admin=true`** (tức là bật được), nhưng đây là **thao tác chính sách của Owner**,
nên harness **không tự bật**. Đã tạo script in ra lệnh chính xác. Tên 5 check trong script đã được
**so từng ký tự** với tên check thật trên GitHub — **khớp**. (Bản in đầu dùng `printf %q` làm hỏng
tên tiếng Việt `Chromium thật`; đã sửa sang dạng dán được.)

---

## 26. SR-2 — TURNSTILE NỐI TRỌN ĐƯỜNG + RANH GIỚI XÁC THỰC

### 26.1 Vấn đề thật đã sửa

Backend **đã** có adapter xác minh token từ trước, nhưng frontend **chưa có widget** và
`TURNSTILE_SITE_KEY` **chưa được mã đọc**. Hệ quả: "bật Turnstile qua biến môi trường" trên thực tế
**không bật được** — bật `TURNSTILE_REQUIRED=true` là **chặn mọi lead** (403). Nay đã nối đủ:

| Thành phần | Việc |
|---|---|
| `app/config.py` | `turnstile_site_key` + `turnstile_enabled` (cần **cả** site **và** secret) |
| `app/routers/public_config.py` | `GET /api/public-config` — trả `enabled`, `site_key`, `warning`; **không** có secret |
| `app/security.py` | `build_strict_csp(turnstile=…)` — **chỉ** mở `challenges.cloudflare.com` khi bật |
| `assets/js/turnstile.js` | Nạp script + render widget; tắt thì **không nạp gì từ Internet** |
| `assets/js/app.js` | Gắn token vào payload; chặn gửi và nói rõ khi bật mà chưa có token |

### 26.2 Ranh giới xác thực — kiểm bằng LIỆT KÊ, không bằng danh sách viết tay

`tests/test_auth_boundary.py` đi qua **toàn bộ route /api lấy từ `app.openapi()`** và khẳng định
mọi route **không** nằm trong danh sách công khai đều trả **401/403/503**. Đo được: **14 route**
(6 công khai có chủ đích + **8 có khoá**, gồm toàn bộ `/api/admin/*` và
`POST /api/gifts/{code}/redeem`). Thêm route mới mà quên gắn xác thực ⇒ test **tự động đỏ**.

> **Bẫy đã dính khi viết test này:** bản đầu duyệt `app.routes`, nhưng FastAPI mới giữ router
> được include dưới dạng lồng (`_IncludedRouter`) chứ không làm phẳng ⇒ liệt kê ra **0 route** và
> test "đạt" một cách **vô nghĩa**. Đã chuyển sang `app.openapi()`, và thêm khẳng định
> `checked > 0` để không bao giờ lặp lại kiểu đạt-rỗng đó.

### 26.3 BỐN ĐỐI CHỨNG ÂM — đo, có kiểm rằng đột biến đã áp dụng

| # | Đột biến | Khi PHÁ | Sau PHỤC |
|---|---|---|---|
| NC-A | Thêm route `/api/admin/*` **mới** không gắn `require_staff` | **1 failed** | 1 passed |
| NC-B | Bỏ chặn khi **thiếu token** (đã cấu hình secret) | **1 failed** | 1 passed |
| NC-C | `/api/public-config` trả **luôn cả secret** | **1 failed** | 1 passed |
| NC-D | CSP mở sẵn Cloudflare **kể cả khi Turnstile tắt** | **1 failed** | 1 passed |

Mỗi ca đều khẳng định **file đã đổi thật** (+/- ký tự) và **khôi phục nguyên trạng = True**.

> **Bài học thứ hai trong cùng một mục:** lần chạy đối chứng âm đầu tiên dùng one-liner shell làm
> hỏng chuỗi nhiều dòng ⇒ **đột biến không được áp dụng** nhưng vẫn in ra `1 passed`, nhìn như đạt.
> Đã viết lại thành script có bước **kiểm đột biến đã áp dụng**. Đây đúng dạng "phép đo nói dối"
> của §17 — lần này công cụ sai là **chính script đối chứng**.

### 26.4 Chốt chặn CI mới

`Guard — khoá SECRET Turnstile không được lộ phía client`: grep `TURNSTILE_SECRET_KEY` /
`turnstile_secret` trong `assets/` và `*.html`, **kèm đối chứng dương** (mẫu phải bắt được một chuỗi
thật, nếu không thì chốt chặn vô dụng mà vẫn xanh). Đã kiểm tại máy: nhúng secret vào
`assets/js/config.js` ⇒ chốt chặn **đỏ**; gỡ ra ⇒ **xanh**.

### 26.5 Lỗi quy trình của chính phiên này

Nhánh `sr-2` được tạo từ **`develop` LOCAL đang cũ** (`f79834fc`) trong khi `develop` thật đã là
`10a7e085` sau SR-1 — vì chỉ chạy `git fetch` rồi đọc `origin/develop` mà **không cập nhật nhánh
local**. Hệ quả: các mục SR-1 trong danh sách tệp bắt buộc của CI **biến mất** khỏi nhánh.
Đã phát hiện khi mô phỏng chốt `Required files exist` (số tệp **giảm** từ 38 xuống 36 dù vừa thêm
tệp). Đã `git rebase origin/develop` (sạch, không xung đột) rồi **chạy lại toàn bộ**: 42 tệp bắt
buộc, **0 thiếu**, 318 backend + 32 E2E PASS.

**Luật:** trước khi tạo nhánh mới, `git fetch` **và** `git checkout develop && git pull --ff-only`,
rồi mới `git checkout -b`. Đọc `origin/develop` là chưa đủ.
