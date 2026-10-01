# VIP PHONE — MASTER STATUS

> Đây là **nguồn trạng thái chính** của dự án VIP PHONE.
> Mọi gate phải cập nhật file này trước khi mở gate kế tiếp.
> Luật: **không ghi PASS / DONE / READY nếu không có evidence đo được.**
> Chưa chạy thì ghi `NOT RUN`. Chưa deploy thì ghi `NOT DEPLOYED`.

- Cập nhật lần cuối: **2026-10-01 18:30 +07** (2026-10-01T11:30Z)
- Người cập nhật: DEEPSEEK HARNESS — VIP PHONE PROJECT CONTROLLER
- Repo: <https://github.com/thanhbn123/vipphone>

---

## 1. BASELINE (Phase 0 — đo ngày 2026-10-01)

| Hạng mục | Giá trị đo được | Cách đo |
|---|---|---|
| Repo | `thanhbn123/vipphone` | `gh repo view` |
| Visibility | **PUBLIC** | `gh repo view --json visibility` |
| Default branch | `main` | `gh repo view --json defaultBranchRef` |
| Tổng số commit | **1** | `git log --all --oneline \| wc -l` |
| Tổng số file tracked | **14** | `git ls-files \| wc -l` |
| MAIN SHA | `7d6162cf31eb96ea27879be3a4671812a9cd7e01` | `git rev-parse origin/main` |
| DEVELOP SHA | `7d6162cf31eb96ea27879be3a4671812a9cd7e01` | `git rev-parse origin/develop` |
| merge-base main↔develop | `7d6162cf31eb96ea27879be3a4671812a9cd7e01` | `git merge-base` |
| Drift main↔develop | **KHÔNG** (hai nhánh trùng SHA) | so SHA |
| OPEN ISSUES | **0** (lúc đo) | `gh issue list --state all` |
| OPEN PRS | **0** | `gh pr list --state all` |
| Branch protection `main` | **KHÔNG có** (HTTP 404) | `gh api .../branches/main/protection` |
| Workflow files | `1` — `.github/workflows/ci.yml` | `git ls-files .github` |

### 1.1 Trạng thái CI tại baseline — **ĐỎ**

| Run ID | Branch | Event | Tạo lúc | Kết quả | Thời lượng |
|---|---|---|---|---|---|
| `36851365921` | `main` | push | 2026-10-01T10:47:56Z | **failure** | 7s |
| `36851427093` | `develop` | push | 2026-10-01T10:48:31Z | **failure** | 8s |

**Nguyên nhân gốc (đo được, không suy đoán):** bước `Check no obvious secrets` chạy một
lệnh `! grep -RInE` quét toàn repo với mẫu regex nhận diện các **tiền tố token phổ biến**:
token GitHub PAT (`ghp_`), token GitHub App, khoá API (`sk-`), và khoá riêng tư PEM.
Hai tiền tố đầu đi kèm lượng từ `[A-Za-z0-9]{20,}`; riêng tiền tố token GitHub App là
**tiền tố trần, không có lượng từ độ dài** — đây là một khuyết điểm của mẫu baseline.

> Phần mô tả trên **cố ý không chép nguyên văn mẫu regex**. Chép nguyên văn sẽ làm chính
> tài liệu này khớp với bước kiểm tra — tái diễn đúng lỗi đang được ghi lại. Xem §1.1.1.

Chính **dòng lệnh đó nằm trong** `.github/workflows/ci.yml`, nên mẫu regex khớp với
chính nó. Log thật của run `36851427093`:

```
./.github/workflows/ci.yml:24:          ! grep -RInE '...' .
##[error]Process completed with exit code 1.
```

`grep` tìm thấy "secret" (là chính mẫu của nó) → exit 0 → `!` đảo thành exit 1 → CI đỏ.
Đây **không phải** secret thật; đây là **bước kiểm tra tự khớp chính nó**.

### 1.1.1 Bài học áp dụng ngay trong tài liệu này

Khi viết lại §1.1 lần đầu, bản nháp **chép nguyên văn mẫu regex cũ** — và bước kiểm tra
mới (G01) lập tức báo đỏ trên chính `docs/MASTER_STATUS.md`:

```
./docs/MASTER_STATUS.md:42:! grep -RInE 'ghp_...' . --exclude-dir=.git
```

Đúng cùng một dạng lỗi, chỉ đổi chỗ. Đã xử lý bằng **hai việc**, không phải bằng nới lỏng
bước kiểm tra:

1. **Sửa tài liệu** — không chép nguyên văn mẫu regex vào văn bản mô tả.
2. **Sửa khuyết điểm thật của mẫu** — tiền tố token GitHub App nay có ràng buộc độ dài
   (`[A-Za-z0-9_]{20,}`) cho đúng hình dạng token thật. Việc này **bớt dương tính giả,
   không giảm khả năng phát hiện token thật**. Tiền tố trần là lỗi của bản baseline: nó
   khớp cả câu văn mô tả nó.

**Thay công cụ chính:** bỏ secret grep tự chế, dùng **gitleaks 8.30.1** quét toàn bộ lịch
sử git (`gitleaks git --no-banner --redact --exit-code 1`). Gitleaks nhận diện theo quy tắc
có cấu trúc nên không tự khớp cấu hình của nó. Vẫn giữ thêm lớp grep nhẹ, nhưng mẫu được
**ghép từ nhiều mảnh chuỗi** trong file workflow để file đó không chứa chuỗi hoàn chỉnh.

### 1.2 Cây thư mục (baseline)

```
.github/workflows/ci.yml
.gitignore
README.md
assets/css/styles.css
assets/js/app.js
assets/js/qr-lite.js
assets/js/redeem.js
assets/js/success.js
data/iphone-models.json
docs/architecture.md
docs/lead-schema.md
index.html
redeem.html
success.html
```

### 1.3 Tech stack baseline

| Lớp | Hiện trạng |
|---|---|
| Frontend | HTML5 tĩnh + CSS thủ công + JavaScript ES2020 thuần (IIFE/global, không module) |
| Build tool | **KHÔNG có** (không `package.json`, không bundler) |
| Backend | **KHÔNG có** |
| Database | **KHÔNG có** |
| Lưu trữ dữ liệu | `localStorage` trình duyệt |
| Cấu hình | `data/iphone-models.json` (fetch tĩnh) |
| Test | **KHÔNG có** (0 test) |
| CI | 3 bước: kiểm tra file tồn tại, lint JSON, secret grep tự chế |

### 1.4 Kiến trúc hiện tại

**Client-only demo.** Không có tầng server. Toàn bộ "nghiệp vụ" chạy trong trình duyệt khách.

```
index.html ──form──> app.js ──> localStorage["vipphone_leads_v1"]
                                   │
                                   ├─> success.html ──success.js──> đọc localStorage, vẽ QR GIẢ
                                   │
                                   └─> redeem.html ──redeem.js──> đọc/ghi localStorage
```

### 1.5 Lưu trữ dữ liệu hiện tại

| Key | Nội dung | Nơi ghi |
|---|---|---|
| `vipphone_leads_v1` | Mảng JSON toàn bộ lead | `app.js`, `redeem.js` |
| `vipphone_last_gift_code` | Gift code vừa tạo | `app.js`, đọc bởi `success.js` |

**Giới hạn đo được:** lead chỉ nằm trên đúng trình duyệt đã đăng ký. Nhân viên ở máy khác **không thấy** lead. Xoá dữ liệu trình duyệt = mất lead. Không có nguồn chân lý.

### 1.6 QR hiện tại — **NOT_PRODUCTION**

`assets/js/qr-lite.js` → `drawQrLike(container, text, size)`

- Vẽ 29×29 ô, 3 finder pattern ở góc.
- Bit sinh từ FNV-1a hash + XOR-shift PRNG, **không phải** mã QR theo chuẩn ISO/IEC 18004.
- **Không đầu đọc QR nào quét được.** Hình vẽ trông giống QR thật → rủi ro đánh lừa nhân viên.
- **Kết luận: `QR = NOT_PRODUCTION`.** Không được dùng trong vận hành thật.

### 1.7 Luồng lead hiện tại

`index.html` form → `app.js`:

1. `normalizePhone()` — bỏ khoảng trắng, bỏ ký tự không phải số (giữ `+`).
2. `validVNPhone()` — regex `/^(0|\+84)(3|5|7|8|9)\d{8}$/`.
3. Chống trùng: tìm trong localStorage theo `phone` + `iphone_model` + `gift_status !== "CANCELLED"`.
4. `randomGiftCode()` — `crypto.getRandomValues` 6 byte, alphabet 32 ký tự (bỏ `I`,`O`,`0`,`1`) → `VIP-26-XXXXXX`.
5. Ghi localStorage, `track()`, chuyển `success.html`.

**Điểm yếu:** năm `26` hard-code trong `randomGiftCode()`; kiểm tra trùng nằm ở client nên vô hiệu khi đổi trình duyệt; không có idempotency.

### 1.8 Luồng redeem hiện tại

`redeem.html` → `redeem.js`:

1. Đọc `?code=` hoặc ô nhập.
2. `findIndex` trong localStorage.
3. Nếu `REDEEMED` → cảnh báo. Nếu không → hiện chi tiết + nút xác nhận.
4. Ghi `gift_status = "REDEEMED"`, `redeemed_at`, `redeemed_by = "LOCAL_STAFF"`.

**Điểm yếu:** quyết định trạng thái cuối nằm ở client; hai nhân viên trên hai máy có thể phát quà hai lần; không atomic; không audit.

### 1.9 Tracking hiện tại

`window.dataLayer` (kiểu GTM), **không** có GTM/GA4/consent thật.

| Event | Nơi phát | Trạng thái |
|---|---|---|
| `vipphone_landing_view` | inline `index.html` | có |
| `vipphone_form_start` | `app.js` | có |
| `vipphone_lead_submit` | `app.js` | có |
| `vipphone_gift_code_created` | `app.js` | có |
| `vipphone_gift_redeemed` | `redeem.js` | có |

**Điểm yếu:** chỉ bắt UTM **tại thời điểm submit**; điều hướng nội bộ làm mất tham số; `success.html` và `redeem.html` không khởi tạo `dataLayer` trước khi script chạy.

### 1.10 Test coverage hiện tại

**0 test.** Không unit test, không integration test, không E2E, không test migration.
Bước CI hiện có chỉ kiểm: file tồn tại, JSON hợp lệ, secret grep.

### 1.11 Lỗ hổng bảo mật hiện tại

| # | Lỗ hổng | Mức | Ghi chú |
|---|---|---|---|
| S1 | Không có server → không thể validate server-side | CAO | Toàn bộ validation ở client, sửa được bằng DevTools |
| S2 | PII (họ tên, SĐT, công ty) lưu ở localStorage không mã hoá | CAO | Bất kỳ script cùng origin đều đọc được |
| S3 | Không có xác thực nhân viên — `redeem.html` mở công khai | CAO | Bất kỳ ai cũng xác nhận phát quà |
| S4 | Không có rate limit / chống spam | CAO | Form có thể bị bơm lead hàng loạt |
| S5 | Không có audit trail | CAO | Không truy vết được ai phát quà, khi nào |
| S6 | Redeem không atomic → double-spend | CAO | Hai máy cùng phát quà cho một mã |
| S7 | Không có security headers (CSP, X-Frame-Options, …) | TRUNG | Không có server để đặt header |
| S8 | Không có CSRF boundary | TRUNG | Hiện chưa có session/cookie |
| S9 | Gift code 6 ký tự alphabet 32 = 32^6 ≈ 1.07e9 | TRUNG | Đủ cho quy mô nhỏ nhưng nên tăng entropy |
| S10 | Không có secret scanning thật (chỉ grep tự chế, lại đang ĐỎ) | TRUNG | Sửa ở G01 bằng gitleaks |
| S11 | Không có `ref`/`src` validation, không whitelist nguồn | THẤP | Có thể nhét rác vào cột `source` |
| S12 | `redeem_by = "LOCAL_STAFF"` hard-code | THẤP | Không định danh được nhân viên |
| S13 | Không có `Referrer-Policy`, không có consent log | THẤP | — |
| S14 | Không có kiểm tra dependency (chưa có dependency) | THẤP | Sẽ có sau G02 |

### 1.12 Rủi ro baseline

| Rủi ro | Ảnh hưởng | Giảm thiểu |
|---|---|---|
| QR giả trông như QR thật | Nhân viên/khách tưởng quét được → hỏng trải nghiệm tại điểm phát quà | G01: ngừng vẽ hình giả; G02: QR chuẩn |
| CI đỏ thường trực | Thói quen bỏ qua CI → mất tác dụng quality gate | G01: sửa bằng công cụ thật |
| Không có nguồn chân lý lead | Mất lead, không đo được funnel | G02: PostgreSQL + API |
| Không có staging | Không nghiệm thu được thật | G11: `BLOCKED_EXTERNAL_INFRA` nếu chưa có hạ tầng |

---

## 2. QUYẾT ĐỊNH KIẾN TRÚC

| ADR | Quyết định | Trạng thái |
|---|---|---|
| [ADR-0001](adr/0001-stack-selection.md) | Python + FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL | Accepted |

---

## 3. TRẠNG THÁI GATE

| Gate | Nội dung | Trạng thái | PR | CI | Ghi chú |
|---|---|---|---|---|---|
| Phase 0 | Discovery / Baseline | **DONE** | — | — | File này |
| G01 | Baseline hardening + sửa CI đỏ | IN PROGRESS | — | NOT RUN | Issue #1 |
| G02 | Real backend (API + DB + migration) | NOT STARTED | — | NOT RUN | — |
| G03 | Redeem engine + audit log | NOT STARTED | — | NOT RUN | — |
| G04 | Staff redeem UI + auth boundary | NOT STARTED | — | NOT RUN | — |
| G05 | Admin leads | NOT STARTED | — | NOT RUN | — |
| G06 | iPhone catalog | NOT STARTED | — | NOT RUN | — |
| G07 | Campaign / source tracking | NOT STARTED | — | NOT RUN | — |
| G08 | Security pass | NOT STARTED | — | NOT RUN | — |
| G09 | Tests | NOT STARTED | — | NOT RUN | — |
| G10 | CI | NOT STARTED | — | NOT RUN | — |
| G11 | Staging readiness | NOT STARTED | — | NOT RUN | — |
| G12 | Owner acceptance pack | NOT STARTED | — | NOT RUN | — |

---

## 4. TRẠNG THÁI HIỆN TẠI (tóm tắt một dòng mỗi mục)

| Mục | Trạng thái |
|---|---|
| LANDING | Có, client-only, chưa hardening |
| LEAD API | **KHÔNG CÓ** |
| DUPLICATE POLICY | Có ở client (localStorage), không hiệu lực |
| GIFT CODE | Sinh ở client, năm hard-code |
| QR | **NOT_PRODUCTION** (QR giả) |
| REDEEM | Client-side, không atomic |
| AUDIT | **KHÔNG CÓ** |
| ADMIN | **KHÔNG CÓ** |
| IPHONE CATALOG | JSON tĩnh, `2025`/`2026` rỗng |
| TRACKING | dataLayer 5 event, chưa nối đích |
| SECURITY | 14 lỗ hổng đã liệt kê ở §1.11 |
| TESTS | **0 test** |
| CI | **ĐỎ** (2/2 run failure) |
| STAGING | **NOT DEPLOYED** |
| PRODUCTION | **NOT DEPLOYED** |

---

## 5. CÁCH ĐO LẠI (evidence commands)

```bash
# Baseline
gh repo view thanhbn123/vipphone --json defaultBranchRef,visibility
git rev-parse origin/main origin/develop
git merge-base origin/main origin/develop
gh issue list --repo thanhbn123/vipphone --state all
gh pr list   --repo thanhbn123/vipphone --state all
gh run list  --repo thanhbn123/vipphone --limit 20
gh api repos/thanhbn123/vipphone/branches/main/protection

# Chất lượng
make lint && make test        # sau G10
gitleaks git --no-banner --redact
```

---

## 6. LUẬT KHÔNG ĐƯỢC VI PHẠM

- **KHÔNG** sửa trực tiếp `main`.
- **KHÔNG** sửa trực tiếp production/VPS.
- **KHÔNG** force push `main`/`develop`.
- **KHÔNG** bỏ qua CI.
- **KHÔNG** commit secret / credential.
- **KHÔNG** tự deploy production khi chưa có release gate của Owner.
- **KHÔNG** sửa code đang LOCKED nếu không có CR mới.
- **PRODUCTION DEPLOY = FORBIDDEN** trong phiên này.

### 6.1 Luật drift trước mọi merge

Đo **expected develop SHA** · **actual develop SHA** · **PR HEAD** · **merge-base**.
Nếu `develop` lệch khỏi giá trị mong đợi → **STOP MERGE**, reconcile trước. Không merge mù.
