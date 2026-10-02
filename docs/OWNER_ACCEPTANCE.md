# NGHIỆM THU CỦA OWNER — VIP PHONE

- Ngày đo: **2026-10-01** (giờ máy +07)
- Người đo: DEEPSEEK HARNESS — VIP PHONE PROJECT CONTROLLER
- Repo: <https://github.com/thanhbn123/vipphone>
- `develop`: `8a417fd0c00de62809eef91d79e0c242593cb33a` — **đã triển khai lên STAGING THẬT**
- `main`: `7d6162cf31eb96ea27879be3a4671812a9cd7e01` — **KHÔNG ĐỔI**
- **STAGING: ĐÃ TRIỂN KHAI** tại `http://160.22.170.20:18080` (SHA trên)
- **STAGING: NOT DEPLOYED** · **PRODUCTION: NOT DEPLOYED**

> **Cách đọc bảng này.** Mục ghi `PASS` **chỉ khi** có lệnh đã chạy hoặc số đo đứng sau.
> Mục chưa đo được thì ghi `BLOCKED` kèm lý do — **không** suy từ "chắc là chạy được".
> Đọc thêm **§C — bảng này KHÔNG nói gì** trước khi kết luận.

## Cách tái lập

```bash
# 0. Chuẩn bị
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/playwright install chromium
createdb vipphone_test

# 1. Backend + integration (PostgreSQL 16 THẬT — không dùng SQLite)
TEST_DATABASE_URL='postgresql+psycopg://<user>:<pw>@localhost:5432/vipphone_test' \
  .venv/bin/python -m pytest -q

# 2. E2E trình duyệt THẬT + API THẬT + PostgreSQL THẬT
TEST_DATABASE_URL='postgresql+psycopg://<user>:<pw>@localhost:5432/vipphone_test' \
  .venv/bin/python -m pytest tests_e2e -q

# 3. Lint + secret
make lint && make secret-scan
```

---

## A. Checklist nghiệm thu

| # | Hạng mục | Kết quả | Evidence |
|---|---|---|---|
| 1 | **LANDING** | **PASS** | E2E `test_landing_emits_view_event_and_loads_catalog_from_api`: landing vẽ **28 `<option>`** đọc từ `/api/catalog/iphone-models`; nút gửi **bị khoá** cho tới khi danh mục sẵn sàng. E2E `test_landing_has_no_inline_script_style_or_handler`: **0** script/style/handler nội tuyến |
| 2 | **LEAD SUBMIT** | **PASS** | E2E `test_full_funnel_creates_lead_with_canonical_phone_and_public_qr`: 1 dòng trong PostgreSQL, `phone = 0912345678` (từ `+84 912 345 678`), `gift_status = NEW`, `consent = true`; 4 event `dataLayer` phát ra |
| 3 | **DUPLICATE** | **PASS** | `tests/test_leads_api.py::test_duplicate_submission_returns_existing_gift` + `test_duplicate_policy_normalizes_phone` (gửi `+84…` so với `09…` → **cùng** gift code, DB chỉ **1** lead); `test_cancelled_gift_does_not_block_new_gift` chứng minh gift đã huỷ **không** chặn cấp mới. E2E xác nhận lại trên trình duyệt thật |
| 4 | **GIFT CODE** | **PASS** | `test_gift_codes_are_unique_in_practice` (2000 mã, 0 đụng độ); `test_gift_code_collision_is_retried` (tiêm đụng độ → **thử lại**, khách không thấy lỗi); `test_gift_code_year_prefix_not_hard_coded`; định dạng `VIP-YY-XXXXXX` |
| 5 | **QR** | **PASS** | QR chuẩn **ISO/IEC 18004** sinh ở server. Giải mã PNG thật bằng **zxing-cpp** → đúng `…/redeem?code=…`. `test_qr_contains_no_pii`: **không** chứa tên/SĐT/công ty/BNI. Có **đối chứng dương** `test_qr_decoder_can_tell_payloads_apart` chứng minh bộ giải mã phân biệt được hai nội dung. **Đối chứng âm:** tiêm PII vào QR → test PII **FAIL** |
| 6 | **GIFT LOOKUP** | **PASS** | `test_lookup_returns_minimum_fields`, `test_lookup_is_case_insensitive`, `test_lookup_trims_whitespace`, `test_lookup_minimizes_pii` (SĐT `0912***678`; **không** trả UTM/công ty/BNI). Thiếu khoá → **401**; chưa cấu hình → **503** (fail closed) |
| 7 | **REDEEM** | **PASS** | `test_redeem_success`: `gift_status = REDEEMED`, có `redeemed_at`, `redeemed_by = staff:<12 hex>`. E2E bấm nút trên Chromium thật → DB đổi trạng thái, audit ghi `GIFT_STATUS_CHANGED` + `GIFT_REDEEMED` |
| 8 | **DOUBLE REDEEM PREVENTION** | **PASS** | `SELECT … FOR UPDATE` khoá hàng trước khi đọc. Lần hai trả `already_redeemed = true`, **không** đổi `redeemed_at`, audit vẫn **đúng 1** `GIFT_REDEEMED`. **Hai test tất định** + **đối chứng âm đã đo**: bỏ `with_for_update()` → **2 FAIL**; khôi phục → **2 PASS** |
| 9 | **ADMIN** | **PASS** | `tests/test_admin_leads_api.py` (**37** hàm test) + `tests/test_admin_catalog_api.py` (**29**) + `tests/test_admin_pages.py` (**5**). **Mọi** route admin có `Depends(require_staff)` kể cả route chỉ đọc; `test_admin_read_routes_require_staff_auth` + `test_admin_routes_fail_closed_when_staff_auth_not_configured`. **IDOR:** `test_admin_unauthenticated_response_leaks_no_lead_data`, `test_admin_detail_without_auth_does_not_reveal_existence`, `test_admin_detail_is_not_publicly_reachable_by_gift_code`. **Đối chứng âm NC1:** bỏ xác thực route danh sách → 1 failed |
| 10 | **FILTER** | **PASS** | `test_filter_by_phone_matches_partially`, `test_filter_by_phone_does_not_treat_input_as_wildcard`, `test_filter_by_phone_without_digits_matches_nothing`, `test_filter_by_model_source_and_status`, `test_filter_by_date_range`, `test_filter_date_range_reversed_is_rejected`, `test_filter_date_must_be_iso`. **Đối chứng âm NC9** (lọc rỗng thành "không lọc gì" → 1 failed), **NC8b** (bỏ cả hai lớp chống wildcard → 1 failed) |
| 11 | **CSV EXPORT** | **PASS** | `test_csv_uses_the_same_filters_as_the_list` (đo bằng **số dòng**, không bằng lời hứa), `test_csv_blocks_formula_injection_in_customer_name`, `test_csv_blocks_formula_injection_through_other_text_columns`, `test_csv_has_stable_header`, `test_csv_starts_with_utf8_bom_for_excel`, và trần số dòng. **Đối chứng âm NC2** (bỏ chống formula injection → **14 failed**), **NC6** (bỏ trần dòng → 1 failed), **NC7** (CSV bỏ qua bộ lọc → 1 failed) |
| 12 | **TRACKING** | **PASS (một phần)** | Server nhận và lưu `src/ref/utm_source/utm_medium/utm_campaign/utm_content`; giá trị lạ bị **422** (`test_unsafe_tracking_values_are_rejected`); attribution sống sót qua điều hướng (E2E). **CHƯA** nối GTM/GA4/Meta Pixel — `TRACKING = DATA_LAYER_ONLY` |
| 13 | **MOBILE** | **PASS** | E2E đo **thật**: **0 tràn ngang** tại **375 px, 393 px, 360 px** trên `/` và `/redeem.html`; `test_lead_form_usable_on_mobile` điền **và gửi được** ở 375×667, gift code sinh ra, ảnh QR nằm trọn trong khung (`bounding_box` nằm trong bề rộng) |
| 14 | **SECURITY** | **PASS (còn mục mở)** | Xem **§B** |
| 15 | **CI** | **PASS** | **5 job** (job `e2e` nay là ma trận 3 engine), xanh trên **cả ba** PR đã merge. Đã kiểm **từng step**, không step nào bị skip. Run: `36860688002` (PR #8), `36861758799` (PR #12), **`36862629800` (PR #14 — 5/5 job, gồm `e2e` chạy Chromium thật và `dependency-scan`)**. Run `36851365921` là CI **ĐỎ** của baseline trước khi sửa |
| 16 | **MIGRATION** | **PASS** | `test_upgrade_creates_expected_schema` trên **database tạm riêng**: đủ bảng, 24 cột `leads`, 7 index; `test_no_pending_migration_diff` chạy **`alembic check`** (bắt được model sửa mà quên migration); `test_seed_inserts_exactly_the_verified_models` = **28 model**, không seed năm rỗng; `test_partial_unique_index_enforces_duplicate_policy` chứng minh **UNIQUE INDEX MỘT PHẦN** chặn trùng ở tầng database |
| 17 | **ROLLBACK** | **PASS (một phần)** | Migration: `test_downgrade_removes_everything` — `downgrade base` xoá sạch 3 bảng, **đã đo**. Quy trình rollback ứng dụng ghi ở `docs/deployment.md`. **CHƯA** diễn tập rollback trên hạ tầng vì **chưa có hạ tầng** |

---

## B. SECURITY — chi tiết

### B.1 Đã đo, đã PASS

| Việc | Evidence |
|---|---|
| Validation server-side | `test_invalid_phone_is_rejected` (6 kiểu SĐT sai → 422), `test_missing_consent_is_rejected`, `test_oversized_names_are_rejected` |
| Không tin dữ liệu client | `test_client_cannot_supply_year_or_status` — gửi kèm `iphone_year`/`gift_status`/`lead_id` → **422** |
| SQL injection | `test_sql_injection_attempt_is_stored_as_literal` — chèn `'); DROP TABLE leads;--`, lưu **nguyên văn**, bảng còn nguyên |
| XSS | Escape mọi nội dung người dùng; CSP `script-src 'self'`; E2E khẳng định **0** inline script/style/handler |
| Ranh giới nhân viên **fail closed** | Chưa cấu hình `STAFF_API_KEYS` → **503** cho **cả** tra cứu, phát quà **và mọi route admin** |
| Rate limit | `test_rate_limit_blocks_after_threshold` (3 → 201, tiếp theo **429** + `Retry-After`); `test_forwarded_for_is_ignored_by_default` chứng minh **đổi `X-Forwarded-For` không né được** |
| Security header | `test_security_headers_present_on_html` + E2E: `X-Content-Type-Options`, `X-Frame-Options: DENY`, CSP, `Referrer-Policy`, `Cache-Control: no-store`; HSTS **chỉ** khi HTTPS |
| Host header | `ALLOWED_HOSTS` + `TrustedHostMiddleware`; `test_untrusted_host_is_rejected` (Host lạ → **400**) |
| Giảm PII | Nhân viên chỉ thấy `0912***678`; không trả UTM/công ty/BNI; `sessionStorage` **không** lưu SĐT; khoá nhân viên **không** vào `localStorage` (có chốt chặn trong CI, **đối chứng âm NC11**) |
| Audit không chứa PII | Metadata đi qua **danh sách trắng khoá**; `test_lead_creation_writes_audit_events` khẳng định không có `phone`/`full_name` |
| Secret | `gitleaks git --no-banner --redact` → `no leaks found` trên **toàn bộ** lịch sử |
| Phụ thuộc | `pip-audit --strict` cho **cả hai** file requirements → `No known vulnerabilities found`. **Job này đã bắt được một lỗ hổng thật** (`pytest 8.4.2`, PYSEC-2026-1845, fix 9.0.3) và đã nâng lên `pytest>=9.0.3,<10` |

### B.2 Năm lỗ hổng do rà soát G08 tìm ra — đã vá, có đối chứng âm

| # | Lỗ hổng | Đối chứng âm |
|---|---|---|
| F1 | Trần body kiểm **sau khi đã đọc hết** vào RAM ⇒ trần 8 KB không bảo vệ được gì | phá → **1 failed** |
| F2 | `/api/ready` công khai lộ `migration_head`, `version`, và việc bot protection đang **TẮT** | phá → **1 failed** |
| F3 | Cấu hình CORS là **mã chết** (đọc như đã làm mà chưa làm) | gắn CORS thoáng → **1 failed** |
| F4 | Thiếu `TrustedHostMiddleware` | tắt → **1 failed** |
| F5 | `request_id` khai mà không ai truyền | (sửa kèm, có test `X-Request-ID`) |

### B.3 CÒN MỞ — ghi thẳng

- **Turnstile/reCAPTCHA**: mới có adapter, **chưa có khoá thật** ⇒ bot protection đang **TẮT**
- **Rate limit trong bộ nhớ tiến trình**: `--workers N` ⇒ giới hạn thực tế × N. Cần Redis nếu scale ngang
- **Chưa rà soát PII lọt vào log production**
- **`main` chưa bật branch protection** → cần Owner

---

## C. Bảng này KHÔNG nói gì

Đọc mục này trước khi kết luận "đã xong":

- **Chưa có hạ tầng staging** ⇒ **toàn bộ** số đo là **trên máy**, không phải trên môi trường giống production.
- **Linux: ĐÃ ĐO, nhưng đúng phạm vi.** CI chạy trên **GitHub-hosted `ubuntu-24.04`, Linux x64** — không phải macOS. Bằng chứng: log runner ghi `Operating System: Ubuntu` + `Image: ubuntu-24.04`, và `setup-python-Linux-x64-24.04-Ubuntu-python-3.12.14`.
  Cụ thể đã chạy **trên Linux**: lint · unit · integration PostgreSQL · migration (`alembic upgrade` + `alembic check`) · secret scan · dependency scan · **E2E Chromium/Firefox/WebKit**.
  **Chưa** đo trên Linux: đóng gói artifact, systemd, nginx, TLS, và **chạy thật dưới tải**. Nghĩa là *"mã chạy đúng trên Linux"* đã có bằng chứng; *"triển khai được trên Linux"* thì **chưa**.
  *(Bản trước của tài liệu này ghi "Chưa đo trên Linux. Mọi phép đo chạy trên macOS" — câu đó **sai**: CI đã chạy Linux từ lâu. Đã sửa.)*
- **Các phép đo "tại máy" là macOS** (Mac mini M4). Chỗ nào ghi "đo tại máy" thì đó là macOS; chỗ nào ghi CI thì đó là Linux.
- **Chưa đo tải.** Không có thử đồng thời, không có đo độ trễ dưới tải.
- **Chưa đo khả năng chịu lỗi database** (mất kết nối giữa chừng, failover).
- **Chưa có sao lưu, chưa thử phục hồi.**
- **Trình duyệt: ĐÃ chạy ma trận 3 engine** — **Chromium**, **Firefox**, **Playwright WebKit**, mỗi engine **33/33 PASS** (trong CI và tại máy).
  - **`SAFARI REAL` = NOT TESTED.** *Playwright WebKit **không phải** Safari thật.* Cùng nhân WebKit nhưng khác bản dựng, khác hệ điều hành, khác tích hợp. Không được ghi "Safari đã kiểm".
  - **Quét QR bằng `BarcodeDetector`: KHÔNG engine nào trong ma trận có API này** — đo được `chromium=False, firefox=False, webkit=False` (kể cả Chromium headless của Playwright). Nghĩa là **nhánh "có hỗ trợ quét" chỉ được kiểm bằng GIẢ LẬP** trong test của G04, **chưa** được kiểm bằng engine thật. Trên máy thật (Chrome desktop có camera) hành vi có thể khác — **chưa đo**.
- **Số test thay đổi theo gate** — con số phải đọc kèm SHA ở đầu tài liệu.
- **Đối chứng âm có phạm vi.** Tổng cộng đã đo **24 ca** (16 của gate G04-G06, 4 của G08, 2 của G09/G10, 2 tất định của G03). Con số đó phủ **các test an ninh và các bản vá cụ thể**, **KHÔNG** có nghĩa "toàn bộ test của dự án đã được đối chứng âm".

---

## D. Việc cần Owner quyết

1. **Hạ tầng staging** (máy chủ + tên miền) — điều kiện để có `STAGING = DEPLOYED`. Không có thì mọi thứ dừng ở mức "đã đo trên máy". → `BLOCKED_EXTERNAL_INFRA`
2. **Khoá Turnstile/reCAPTCHA** — để bật bot protection thật.
3. **Bật branch protection cho `main`** (bắt buộc PR + CI xanh) — hiện đang **TẮT**.
4. **Lệnh release production** — **chưa có**, nên PRODUCTION vẫn **NOT DEPLOYED**. Phiên này **KHÔNG** deploy production và **KHÔNG** merge `main`.
5. **Chính sách lưu trữ PII** — lưu lead và log IP bao lâu? (3 phương án ở `docs/decisions/PII_RETENTION_OPTIONS.md`)
6. **RPO/RTO và lịch sao lưu** — mất tối đa bao nhiêu dữ liệu là chấp nhận được? Giữ bản sao lưu bao lâu, ở đâu? Xem `docs/backup-restore.md` §4.

Toàn bộ danh sách kèm hướng dẫn thao tác: **`docs/OWNER_DECISIONS_REQUIRED.md`**.

---

## E. Trạng thái gate

| Gate | Nội dung | Trạng thái |
|---|---|---|
| G01 | Baseline hardening + sửa CI đỏ | **DONE** |
| G02 | Backend thật: API + PostgreSQL + migration + QR chuẩn + catalog | **DONE** |
| G03 | Redeem engine nguyên tử + audit | **DONE** |
| G04+G05+G06 | Staff UI quét QR, admin leads/CSV, danh mục qua admin | **DONE** |
| G07 | Campaign / source tracking | **DONE** (một phần: `dataLayer` only) |
| G08 | Security pass | **DONE** |
| G09+G10 | Tests đầy đủ + CI đầy đủ (5 job) | **DONE** |
| G11+G12 | Staging readiness + gói nghiệm thu này | **DONE** |
| **SR-1** | Hợp đồng cấu hình staging + bản đồ PII + phương án retention | **DONE** |
| **SR-2** | Nối trọn đường Turnstile qua env + ranh giới xác thực kiểm bằng liệt kê | **DONE** |
| **SR-3** | Ma trận trình duyệt Chromium/Firefox/WebKit + sửa câu SAI về Linux | **DONE** |
| **SR-4** | Preflight staging + sao lưu/phục hồi + smoke tải + phát hành/quay lui | **DONE** |

Xem `docs/MASTER_STATUS.md` để biết trạng thái chi tiết và SHA từng gate.

---

## F. STAGING READINESS — trạng thái repo-side

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Hợp đồng cấu hình | **PASS** | `docs/staging.md` — 19 biến phân loại REQUIRED/OPTIONAL · SECRET/PUBLIC · BUILD/RUN; 0 biến thiếu so với `Settings.model_fields` |
| Mẫu biến staging | **PASS** | `.env.staging.example` |
| Kiểm trước deploy | **PASS** | `scripts/staging_preflight.sh` — **18 mục**, **6 đối chứng âm** |
| Turnstile adapter | **PASS** | Server xác minh, CSP có điều kiện, widget frontend; **17 test** |
| Turnstile credential thật | **BLOCKED_EXTERNAL_CREDENTIAL** | Chưa có khoá ⇒ bot protection **TẮT** |
| Ranh giới xác thực | **PASS** | **14 route** liệt kê từ `app.openapi()`: 6 công khai + **8 có khoá** |
| Trình duyệt | **PASS** | Chromium **33/33** · Firefox **33/33** · Playwright WebKit **33/33** |
| CI | **PASS** | **7 check**, chạy trên **ubuntu-24.04 Linux x64** |
| Sao lưu / phục hồi | **LOCAL PASS** | `docs/backup-restore.md`; 250 lead, md5 nội dung khớp |
| Smoke tải | **LOCAL PASS** | 14 755 request / 12 s · **0 lỗi thật** · p50 5.1 ms · p95 6.0 ms |
| Bản đồ PII | **PASS** | `docs/pii-data-map.md` |
| Phát hành / quay lui | **PASS (thiết kế)** | `docs/deployment.md` §12 — **chưa chạy trên hạ tầng thật** |
| Hạ tầng staging | **BLOCKED_EXTERNAL_INFRA** | Chưa có máy chủ/domain |
| Branch protection | **OWNER_ACTION_REQUIRED** | `main` và `develop` đều **chưa** được bảo vệ (`404`) |
| Retention PII | **OWNER_DECISION_REQUIRED** | 3 phương án ở `docs/decisions/PII_RETENTION_OPTIONS.md` |

**`REPO_SIDE_STAGING_READINESS = PASS`** — mọi việc làm được ở phía repo đã xong.
Phần còn lại **đều là chặn bên ngoài**, không phải việc code.

### F.1 Wording chính xác cho từng phép đo

| Cách nói SAI | Cách nói ĐÚNG |
|---|---|
| "Safari đã kiểm" | **`PLAYWRIGHT WEBKIT = PASS`** · `SAFARI REAL = NOT TESTED` |
| "đã kiểm Linux" (vì máy Mac chạy được) | **CI Linux PASS** (ubuntu-24.04) · máy là **macOS** |
| "đã kiểm quét QR" | **giả lập** `BarcodeDetector`; **không engine nào** trong ma trận có API thật |
| "đã kiểm tải" | **`LOCAL LOAD SMOKE`** — cùng máy với server, **không** phải benchmark |
| "sao lưu đã chạy" | **`LOCAL BACKUP/RESTORE TEST`** — chưa có lịch tự động, chưa có staging |

---

# GÓI NGHIỆM THU OWNER — bản chốt

## 1. WHAT IS VERIFIED (đã đo, có bằng chứng)

| # | Hạng mục | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | GitHub baseline | PASS | `develop` `8a417fd0`, `main` `7d6162cf` không đổi |
| 2 | CI | PASS | **7 check** xanh; `develop` chạy sau mỗi merge |
| 3 | Migrations | PASS | `current` = `heads` = `0001_initial`; `alembic check` sạch |
| 4 | Staging deployment | PASS | SHA `8a417fd0` từ Git, cây sạch; container `vipphone-staging-app`, RestartCount **0** |
| 5 | Health / Readiness | PASS | **200** qua mạng thật từ máy khác |
| 6 | Landing | PASS | 200, HTML, 3 asset 200, catalog **28** model |
| 7 | Mobile | PASS | **0 px tràn ngang** tại **320 / 375 / 390 / 430 px** |
| 8 | Lead creation | PASS | 201, ghi DB thật, marker test |
| 9 | Duplicate handling | PASS | gửi lại → **cùng** gift code, không tạo dòng thứ hai |
| 10 | Gift code | PASS | `VIP-26-XXXXXX`, UNIQUE, đụng độ thì thử lại |
| 11 | QR | PASS | giải mã bằng **zxing-cpp** (độc lập) → đúng domain staging, **không PII** |
| 12 | Staff auth | PASS | không khoá **401** · sai **401** · đúng **200** |
| 13 | Admin | PASS | list / filter / CSV 200; CSV có **BOM UTF-8**, header đúng |
| 14 | Redeem | PASS | 200, `REDEEMED`, audit ghi 1 lần |
| 15 | Concurrent redeem | PASS | **8 đồng thời → ĐÚNG 1 lần phát thật**, 7 `already_redeemed` |
| 16 | Audit | PASS | 4 loại event; **0 bản ghi chứa GIÁ TRỊ PII** |
| 17 | Chromium | PASS | landing + 28 model + form |
| 18 | Firefox | PASS | như trên |
| 19 | WebKit | PASS | như trên (**KHÔNG phải Safari** — xem §2) |
| 20 | Load smoke | PASS | **3802 req / 14.9 s** · **0 lỗi thật** · p50 **21.3 ms** · p95 **34.2 ms** · p99 **110 ms** · CPU **0.16%** · RAM app 79 MiB · DB conn 6→10 · **restart 0** |
| 21 | Backup | PASS | 0.17 s · 15 172 byte |
| 22 | Restore | PASS | 0.13 s vào DB **TẠM**; số dòng khớp; **md5 nội dung khớp**; 4 bảng |
| 23 | Rollback | PASS | `1d651f46` ⇄ `04c15828`, health/ready/landing **200 cả hai lượt**, **image SHA đổi thật** |
| 24 | Logs | PASS | 0 secret · 0 `DATABASE_URL` · **0 Traceback** · 0 lỗi 5xx |
| 25 | Test data cleanup | PASS | chỉ xoá dòng có marker; từ chối production; khách thật còn nguyên |
| 26 | Security scans | PASS | gitleaks **no leaks**; pip-audit `--strict` **0 lỗ hổng** |
| 27 | Branch protection | PASS | `main` và `develop`: 7 check, `strict`, cấm force push, cấm xoá |

## 2. WHAT IS NOT VERIFIED

| Hạng mục | Trạng thái | Lý do |
|---|---|---|
| **Turnstile thật** | **BLOCKED_EXTERNAL_CREDENTIAL** | Chưa có khoá site + secret. Test hiện có dùng **verifier giả** — chứng minh *đường đi*, **không** chứng minh *tích hợp Cloudflare*. Bot protection đang **TẮT** |
| **Domain + TLS** | **BLOCKED_OWNER_ACTION** | Staging là `http://160.22.170.20:18080`. `deploy` **không có sudo** nên không sửa được reverse proxy dùng chung. **Chưa có HTTPS** |
| **`SAFARI REAL`** | **NOT TESTED** | Playwright WebKit **không phải** Safari thật (khác bản dựng, khác tích hợp) |
| Quét QR bằng camera | **NOT TESTED** | **Không engine nào** trong ma trận có `BarcodeDetector` (đo: chromium/firefox/webkit = False). Nhánh "có hỗ trợ quét" chỉ được kiểm bằng **giả lập** |
| Staging preflight **trên host** | **NOT RUN** | Script đã có và đã chạy ở LOCAL (18 mục, 6 đối chứng âm); **chưa** chạy trong môi trường staging |
| Reverse proxy / TLS termination | **NOT_CONFIGURED** | Không có domain |
| Đo trên Linux **tại máy này** | N/A | Máy đo là **macOS**; CI chạy Linux (ubuntu-24.04) và **staging chạy Linux** (Ubuntu 26.04) |

## 3. WHAT OWNER MUST DECIDE

| # | Quyết định | Trạng thái |
|---|---|---|
| D-002 | **Khoá Turnstile** (site + secret) | `BLOCKED_EXTERNAL_CREDENTIAL` |
| D-004 | **Chính sách lưu trữ PII** — 3 phương án ở `docs/decisions/PII_RETENTION_OPTIONS.md` | `OWNER_DECISION_REQUIRED` |
| D-005 | **RPO/RTO + lịch sao lưu** — số đo thật ở `docs/backup-restore.md` §4 | `OWNER_DECISION_REQUIRED` |
| — | **Domain + TLS cho staging** (và/hoặc cấp quyền cấu hình reverse proxy) | `OWNER_ACTION_REQUIRED` |

## 4. WHAT WILL HAPPEN AFTER OWNER APPROVAL

1. Cấu hình domain + TLS cho staging; chạy lại `scripts/staging_preflight.sh` trong môi trường thật
2. Bật Turnstile thật khi có khoá; kiểm **valid / invalid / missing token** trên staging (không mock)
3. Diễn tập phát hành: merge `develop` → `main` **chỉ khi Owner ra lệnh release**
4. Triển khai production theo `docs/deployment.md` §12 (9 bước, **sao lưu trước khi đổi schema**)
5. Kiểm tay 1 lead thật trên production (bước 8 — test tự động **không** thay được)
6. Ghi biên bản phát hành kèm SHA

**Chưa có lệnh release nào ⇒ `main` không đổi và production không được triển khai.**

## 5. Phạm vi — đọc cho đúng

- Mọi số đo **trên staging** là tại `160.22.170.20`, một VPS **dùng chung** với staging của dự án khác (`vip-vtelpost`); đã tách network/DB/container/cổng.
- Staging chạy **HTTP, không TLS**. Một số cảnh báo trình duyệt (ví dụ `Cross-Origin-Opener-Policy ... untrustworthy origin`) là **hệ quả của HTTP**, không phải lỗi ứng dụng.
- Load smoke **nhỏ và ngắn** — **không** suy ra được năng lực chịu tải production.
- **Hai lỗi thật do staging tìm ra** (STG-1 thiếu `httpx`, STG-2 favicon 204 kèm body) — cả hai **đã sửa**, đều có **đối chứng âm**. Điều này cho thấy CI một mình **không đủ**; staging là gate có giá trị riêng.
