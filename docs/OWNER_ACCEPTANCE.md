# NGHIỆM THU CỦA OWNER — VIP PHONE

- Ngày đo: **2026-10-01** (giờ máy +07)
- Người đo: DEEPSEEK HARNESS — VIP PHONE PROJECT CONTROLLER
- Repo: <https://github.com/thanhbn123/vipphone>
- `develop`: `d4648f46cd801cf323b715a3eba334ff3570ca4e` *(đo trước khi gate G11+G12 merge)*
- `main`: `7d6162cf31eb96ea27879be3a4671812a9cd7e01` — **KHÔNG ĐỔI suốt phiên**
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
| 15 | **CI** | **PASS** | **5 job**, xanh trên **cả ba** PR đã merge. Đã kiểm **từng step**, không step nào bị skip. Run: `36860688002` (PR #8), `36861758799` (PR #12), **`36862629800` (PR #14 — 5/5 job, gồm `e2e` chạy Chromium thật và `dependency-scan`)**. Run `36851365921` là CI **ĐỎ** của baseline trước khi sửa |
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
- **Chưa đo trên Linux.** Mọi phép đo chạy trên macOS (Mac mini M4). Lần chạy đầu trên Linux phải coi là **chưa biết**, không phải "đã biết".
- **Chưa đo tải.** Không có thử đồng thời, không có đo độ trễ dưới tải.
- **Chưa đo khả năng chịu lỗi database** (mất kết nối giữa chừng, failover).
- **Chưa có sao lưu, chưa thử phục hồi.**
- **Chưa đo trên trình duyệt khác Chromium** — E2E chỉ chạy Chromium. Quét QR chỉ chạy trên trình duyệt có `BarcodeDetector`; Safari/iOS và Firefox sẽ **ẩn nút** (đúng thiết kế, nhưng **chưa thử thật**).
- **Số test thay đổi theo gate** — con số phải đọc kèm SHA ở đầu tài liệu.
- **Đối chứng âm có phạm vi.** Tổng cộng đã đo **24 ca** (16 của gate G04-G06, 4 của G08, 2 của G09/G10, 2 tất định của G03). Con số đó phủ **các test an ninh và các bản vá cụ thể**, **KHÔNG** có nghĩa "toàn bộ test của dự án đã được đối chứng âm".

---

## D. Việc cần Owner quyết

1. **Hạ tầng staging** (máy chủ + tên miền) — điều kiện để có `STAGING = DEPLOYED`. Không có thì mọi thứ dừng ở mức "đã đo trên máy". → `BLOCKED_EXTERNAL_INFRA`
2. **Khoá Turnstile/reCAPTCHA** — để bật bot protection thật.
3. **Bật branch protection cho `main`** (bắt buộc PR + CI xanh) — hiện đang **TẮT**.
4. **Lệnh release production** — **chưa có**, nên PRODUCTION vẫn **NOT DEPLOYED**. Phiên này **KHÔNG** deploy production và **KHÔNG** merge `main`.
5. **Chính sách lưu trữ PII** — lưu lead và log IP bao lâu?

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

Xem `docs/MASTER_STATUS.md` để biết trạng thái chi tiết và SHA từng gate.
