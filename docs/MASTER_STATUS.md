# VIP PHONE — MASTER STATUS

> **Nguồn trạng thái chính của dự án VIP PHONE.**
> Mọi gate phải cập nhật file này trước khi mở gate kế tiếp.
>
> **Luật:** không ghi PASS / DONE / READY nếu không có evidence đo được.
> Chưa chạy thì ghi `NOT RUN`. Chưa deploy thì ghi `NOT DEPLOYED`.
> Kết luận dạng "0 lỗi" phải ghi kèm **công cụ đo**, **phạm vi đo** và **cái nằm ngoài phạm vi**.

- Cập nhật lần cuối: **2026-10-01, 19:05 +07**
- Người cập nhật: DEEPSEEK HARNESS — VIP PHONE PROJECT CONTROLLER
- Repo: <https://github.com/thanhbn123/vipphone>

---

## 1. TRẠNG THÁI GATE

| Gate | Nội dung | Trạng thái | PR | CI | Merge SHA vào develop |
|---|---|---|---|---|---|
| Phase 0 | Discovery / Baseline | **DONE** | — | — | — |
| G01 | Baseline hardening + sửa CI đỏ | **DONE** | [#2](https://github.com/thanhbn123/vipphone/pull/2) | **PASS** | `7dabe0ade68797a6eead65dd315924f52748987a` |
| G02 | Real backend (API + DB + migration + QR chuẩn + catalog) | **IN PROGRESS** | — | NOT RUN | — |
| G03 | Redeem engine (atomic, chống double-spend) + audit | NOT STARTED | — | NOT RUN | — |
| G04 | Staff redeem UI + xác thực nhân viên | NOT STARTED | — | NOT RUN | — |
| G05 | Admin leads | NOT STARTED | — | NOT RUN | — |
| G06 | iPhone catalog | MỘT PHẦN (đã có ở G02: DB + seed + API) | — | — | — |
| G07 | Campaign / source tracking | MỘT PHẦN (đã có ở G02: nhận & lưu ở server) | — | — | — |
| G08 | Security pass | MỘT PHẦN (đã có ở G02: header, rate limit, auth boundary) | — | — | — |
| G09 | Tests đầy đủ | MỘT PHẦN (143 test backend; E2E trong repo chưa có) | — | — | — |
| G10 | CI đầy đủ | MỘT PHẦN (lint, migration, unit, integration PG, secret scan) | — | — | — |
| G11 | Staging readiness | MỘT PHẦN (`.env.example`, `/api/ready` đã có; `docs/deployment.md` chưa) | — | — | — |
| G12 | Owner acceptance pack | NOT STARTED | — | NOT RUN | — |

**Baseline gốc của dự án:** `7d6162cf31eb96ea27879be3a4671812a9cd7e01` (1 commit, 14 file, CI đỏ 2/2 run).
Chi tiết baseline đầy đủ nằm ở lịch sử git (`git show 7d6162c`) và ở PR #2.

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
| POST | `/api/gifts/{gift_code}/redeem` | **nhân viên** | **CHƯA CÓ** → G03 |
| GET | `/api/admin/leads` | **nhân viên** | **CHƯA CÓ** → G05 |

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
| Xác nhận phát quà (ghi trạng thái) | **CHƯA CÓ** → G03 |
| Giao dịch nguyên tử / chống double-spend | **CHƯA CÓ** → G03 |
| Audit `GIFT_REDEEMED` | **CHƯA CÓ** → G03 |

Trang `redeem.html` **nói thẳng** khi chức năng xác nhận chưa khả dụng — không giả vờ thành công.

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
- Thêm model mới = INSERT vào bảng (hoặc qua admin ở G05), **không phải sửa HTML**. Có test.
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
| S5 | Audit trail | **MỘT PHẦN** — lead/gift có; redeem ở G03 |
| S7 | Security header | **CÓ** — CSP nghiêm, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP; HSTS chỉ khi HTTPS |
| S8 | CSRF | Không dùng cookie/session; xác thực qua header nên **không bị CSRF cổ điển**. Ghi rõ để không tưởng là đã làm |
| S10 | Secret scanning | **CÓ** — gitleaks 8.30.1, quét toàn bộ lịch sử git |
| S11 | Whitelist giá trị tracking | **CÓ** |
| S12 | `redeemed_by` hard-code | **XONG** — actor suy từ khoá nhân viên, không hard-code |
| — | PII minimization | Che SĐT (`0912***678`), không trả UTM/công ty/BNI cho nhân viên, không lưu SĐT vào `sessionStorage` |
| — | SQL injection | Tham số hoá toàn bộ qua SQLAlchemy; có test chèn `'); DROP TABLE leads;--` và xác nhận lưu nguyên văn, bảng còn nguyên |
| — | XSS | Escape mọi nội dung người dùng; CSP `script-src 'self'`; **không** inline script/style trong HTML (CI chặn) |

### 13.2 CÒN MỞ (ghi đúng, không tô hồng)

| # | Việc | Gate |
|---|---|---|
| — | Turnstile chỉ có **adapter**, chưa bật ở đâu (chưa có secret thật) | G08 / cần Owner |
| — | Rate limit **trong bộ nhớ tiến trình** → nhiều instance thì mỗi instance đếm riêng. Ghi rõ, **không** giả vờ đủ cho production nhiều instance | G08 |
| — | Chưa có `pip-audit` / dependency scan trong CI | G08 |
| — | Chưa có admin leads (S2: dữ liệu đầy đủ chỉ nên xem ở khu vực có xác thực riêng) | G05 |
| — | Chưa có test IDOR cho route admin (route admin chưa tồn tại) | G05/G08 |
| — | Chưa rà soát PII lọt vào log production | G08 |

---

## 14. TESTS

**143 test, tất cả PASS** — đo bằng `python -m pytest -q` trên **PostgreSQL 16 thật**.
Phạm vi: `tests/` (unit + integration). **Chưa có** bộ E2E nằm trong repo.

| File | Nội dung |
|---|---|
| `tests/test_phone.py` | 30 ca chuẩn hoá SĐT, kể cả idempotent và "mọi cách viết ra một giá trị" |
| `tests/test_giftcodes.py` | định dạng, entropy, không tuần tự, tra cứu hoa/thường |
| `tests/test_health_and_headers.py` | `/api/health`, `/api/ready`, security header, CSP, shortlink |
| `tests/test_leads_api.py` | lead hợp lệ, SĐT sai, thiếu consent, trùng lặp, gift code duy nhất, đụng độ + thử lại, UTM, model, SQLi, rate limit |
| `tests/test_gifts_api.py` | xác thực, che PII, mã sai, **QR giải mã thật**, danh mục |
| `tests/test_migrations.py` | upgrade/downgrade trên **database tạm riêng**, seed, UNIQUE một phần, CHECK, `alembic check` |

Đối chiếu với 14 kịch bản bắt buộc của G09:

| # | Kịch bản | Trạng thái |
|---|---|---|
| 1 | valid lead | **PASS** |
| 2 | invalid phone | **PASS** |
| 3 | missing consent | **PASS** |
| 4 | duplicate submission | **PASS** |
| 5 | gift code uniqueness | **PASS** |
| 6 | gift lookup | **PASS** |
| 7 | redeem success | **CHƯA** → G03 |
| 8 | redeem second time | **CHƯA** → G03 |
| 9 | concurrent redeem | **CHƯA** → G03 |
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
| `Validate static frontend` | file bắt buộc, JSON hợp lệ, `node --check`, chốt chặn QR giả / QR phải từ server / không quay lại `localStorage` / HTML không inline |
| `Backend (lint, migration, tests)` | PostgreSQL 16 service container, ruff, `alembic upgrade head` + `alembic check`, unit test, integration test, full suite |

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

**Nguyên tắc rút ra:** khi một chốt chặn báo động, câu hỏi đầu tiên phải là
*"chốt chặn sai hay dữ liệu sai?"* — và câu trả lời phải bằng **một phép đo**,
không bằng cảm giác. Bốn lần đầu là **công cụ sai**; lần 5 và 6 là **dữ liệu/thiết lập sai**;
lần 7 là **giá trị thử nghiệm gây nhiễu**. Sửa đúng chỗ, không sửa cho vừa mắt.

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
make lint                     # ruff check + format --check
make test                     # pytest trên PostgreSQL thật
make migrate-check            # alembic upgrade head + alembic check
make secret-scan              # gitleaks toàn bộ lịch sử
```
