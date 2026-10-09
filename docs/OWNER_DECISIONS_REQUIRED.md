# Quyết định cần OWNER — VIP PHONE

> Chỉ chứa những việc **thật sự** cần Owner: cần hạ tầng, cần credential, cần quyền quyết định
> chính sách, hoặc cần thao tác trên kênh thật. **Không** nhét quyết định kỹ thuật nhỏ vào đây.
>
> Đo lần đầu ngày **2026-10-01**; **cập nhật 2026-10-07** sau các gate thương mại (G15–G17, kho,
> lịch sử giá, ảnh, attribution). Mọi thứ repo-side đã xong và **không** chờ các mục dưới đây.

| # | Quyết định | Trạng thái | Chặn cái gì |
|---|---|---|---|
| D-001 | Hạ tầng staging | ✅ **CLOSED** — máy chủ + `qua.viporder.vn` (DNS) + **TLS Let's Encrypt** đều XONG | — |
| D-002 | Credential Turnstile | **BLOCKED_EXTERNAL_CREDENTIAL** | bot protection thật |
| D-003 | Branch protection | ✅ **CLOSED** — đo 2026-10-07: `main` + `develop` bắt buộc PR + đúng 4 check tự động, `strict`, cấm force-push/xoá; đối chứng âm PR #65 bị chặn | — |
| D-004 | Chính sách lưu trữ PII | **CLOSED** — Owner đã chốt 2026-10-02 | — |
| D-005 | RPO/RTO + lịch sao lưu | Chính sách **CLOSED** (2026-10-02) · **lịch chạy tự động: CHƯA CÓ** (đo 2026-10-10) | RPO 24 giờ trên staging |
| D-006 | Đường triển khai staging cho các gate thương mại | ✅ **CLOSED** 2026-10-10 — Owner chạy runbook từ MacBook, 27/27 bước qua | — |
| D-007 | `enforce_admins` của branch protection | **OWNER_DECISION** (hiện `false`) | admin vẫn bypass được check đỏ |
| D-008 | Biểu phí giao hàng | **OWNER_DECISION** (hiện `SHIPPING_FEE_FLAT=0.00`) | tổng đơn thật |
| D-009 | Nội dung chuyển khoản (số TK, ngân hàng, chủ TK) | **OWNER_INPUT** (staging đang dùng câu `[THỬ - STAGING]`, production chưa có) | khách tự chuyển khoản không cần gọi |
| D-010 | Kho ảnh production + sao lưu ảnh | **OWNER_DECISION** (kho production) · sao lưu volume ảnh staging: ✅ có từ 2026-10-10 | ảnh sản phẩm ở production |
| D-011 | Khoá webhook giả lập trên staging | ✅ **CLOSED** 2026-10-10 — sinh TRÊN máy chủ (runbook §1), webhook ký đúng ⇒ APPLIED, gửi lại ⇒ DUPLICATE, ký sai ⇒ 401 | — |
| — | Cổng thanh toán thật | **NOT INTEGRATED** (ranh giới cho phép) | thu tiền online thật |

---

## D-001 — HẠ TẦNG STAGING

**Need.** Một máy chủ Linux chạy được tiến trình Python, một PostgreSQL 16, và một tên miền phụ có TLS.

**Vì sao chưa làm được.** Không có máy chủ, không có tên miền, không có DNS. Đây là chặn **bên
ngoài repo** — toàn bộ phần repo-side đã xong.

**Repo-side đã sẵn sàng:**

- [`docs/deployment.md`](deployment.md) — cách triển khai, mô tả **trung lập với hạ tầng**
- [`docs/staging.md`](staging.md) — hợp đồng cấu hình, phân loại từng biến
- [`.env.staging.example`](../.env.staging.example) — mẫu điền
- `scripts/staging_preflight.sh` — kiểm trước khi deploy, thoát mã ≠ 0 nếu chưa đạt

**Required values** (Owner hoặc người dựng staging cung cấp):

| Giá trị | Ví dụ | Ghi chú |
|---|---|---|
| Host / VM | — | Linux, Python 3.12, có thể ra Internet |
| Domain staging | `staging.<domain>` | Phải phân giải được |
| TLS | chứng chỉ cho domain trên | Bắt buộc — `PUBLIC_BASE_URL` phải là `https` |
| PostgreSQL 16 | host, port, db, user, password | **Database RIÊNG**, không trỏ vào production |
| Reverse proxy | nginx/Caddy/Traefik | Phải ghi đè `X-Forwarded-For` |
| `STAFF_API_KEYS` | ≥1 khoá mạnh | Sinh bằng `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

**Options.** Chưa chốt hình thức triển khai. Hai hướng đều dùng được cùng một repo:

- **A — systemd + nginx trên VM.** Đơn giản nhất, ít lớp. Unit và cấu hình nginx mẫu đã có trong
  `docs/deployment.md`.
- **B — container.** Cần thêm `Dockerfile`/`compose` (repo **chưa có**). Chỉ nên chọn nếu đã có sẵn
  hạ tầng container; **không** đáng đổi stack chỉ để container hoá.

**Việc Owner làm:** cấp máy chủ + domain + TLS và database, rồi nói hình thức A hay B.
Sau đó repo-side có thể thêm `Dockerfile` nếu chọn B.

---

## D-002 — CREDENTIAL TURNSTILE

**Need.**

| Giá trị | Loại | Lấy ở đâu |
|---|---|---|
| `TURNSTILE_SITE_KEY` | **PUBLIC** (nằm trong HTML/JS) | Cloudflare dashboard |
| `TURNSTILE_SECRET_KEY` | **SECRET** (chỉ ở server) | Cloudflare dashboard |

**Trạng thái:** **BLOCKED_EXTERNAL_CREDENTIAL**. Chưa có khoá ⇒ bot protection đang **TẮT**.

**⚠️ Đọc trước khi bật `TURNSTILE_REQUIRED=true`.** Xem
[`docs/staging.md`](staging.md) §3 — hiện **frontend chưa có widget**, nên bật cờ này sẽ
**chặn mọi lead** (403). Cờ này chỉ bật được **sau** khi gate nối widget xong.

**Cách nạp an toàn:** đặt vào biến môi trường trên máy chủ (hoặc secret manager). **KHÔNG** commit.
**KHÔNG** dán vào hội thoại. `gitleaks` chạy trong CI sẽ chặn nếu lọt vào repo.

**Repo-side đã sẵn sàng:** adapter xác minh ở **server**, có timeout rõ ràng, có chính sách
fail-open/fail-closed ghi ở `docs/staging.md` §3.1. Phần còn thiếu (widget frontend) thuộc gate sau
và **không** chờ khoá thật.

---

## D-003 — BRANCH PROTECTION — ✅ CLOSED (đo lại 2026-10-07)

Đo bằng GitHub API (`GET /repos/thanhbn123/vipphone/branches/{main,develop}/protection`):

| | `main` | `develop` |
|---|---|---|
| check bắt buộc | `Backend (lint, migration, tests)`, `Dependency scan (pip-audit)`, `Secret scan (gitleaks)`, `Validate static frontend` | như `main` |
| `strict` (phải cập nhật với base) | `true` | `true` |
| bắt buộc PR | có (0 người duyệt) | có (0 người duyệt) |
| force-push / xoá nhánh | cấm / cấm | cấm / cấm |
| `enforce_admins` | **`false`** | **`false`** |

4 check bắt buộc = **đúng 4 job tự động** của `ci.yml`. Ba job E2E chỉ chạy tay (`workflow_dispatch`) và
**không** còn nằm trong danh sách bắt buộc ⇒ PR không bị kẹt bởi check không bao giờ chạy.
(Bản handoff nói "vẫn đòi 3 check E2E" — đo lại thì **đã** được sửa trước lượt này; không cần đổi gì.)

**Đối chứng âm:** PR #65 cố ý thêm import thừa ⇒ job bắt buộc `Backend` **failure** ⇒
`mergeable_state = blocked`. Đã đóng, không merge.

Phần lịch sử bên dưới giữ để tham chiếu.

**Trạng thái đo được ngày 2026-10-01 (cũ):**

```
main    : "Branch not protected"  (HTTP 404)
develop : "Branch not protected"  (HTTP 404)
rulesets: []
```

**Token hiện có `admin=true`** — tức là **có thể** bật được. Nhưng đây là **thao tác của Owner**
(chính sách bảo vệ nhánh, không phải việc kỹ thuật), nên harness **không tự bật**.

**Rủi ro của hiện trạng:** không có gì chặn push thẳng vào `main`. Toàn bộ kỷ luật "chỉ merge qua PR"
hiện dựa vào **quy ước**, không dựa vào **cơ chế**.

**Cách bật:** chạy `scripts/enable_branch_protection.sh` (script chỉ in ra lệnh — **Owner tự chạy**),
hoặc chạy tay 5 lệnh dưới. Tên check **lấy từ GitHub thật**, không phải tự đặt:

```bash
# 1. main — yêu cầu PR + CI xanh, cấm force push và cấm xoá nhánh
gh api -X PUT repos/thanhbn123/vipphone/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks[strict]=true \
  -f 'required_status_checks[contexts][]=Backend (lint, migration, tests)' \
  -f 'required_status_checks[contexts][]=Dependency scan (pip-audit)' \
  -f 'required_status_checks[contexts][]=E2E (chromium thật + PostgreSQL)' \
  -f 'required_status_checks[contexts][]=E2E (firefox thật + PostgreSQL)' \
  -f 'required_status_checks[contexts][]=E2E (webkit thật + PostgreSQL)' \
  -f 'required_status_checks[contexts][]=Secret scan (gitleaks)' \
  -f 'required_status_checks[contexts][]=Validate static frontend' \
  -f enforce_admins=false \
  -f required_pull_request_reviews[required_approving_review_count]=0 \
  -F allow_force_pushes=false \
  -F allow_deletions=false

# 2. develop — cùng bộ check, chặn force push và xoá nhánh
gh api -X PUT repos/thanhbn123/vipphone/branches/develop/protection \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks[strict]=true \
  -f 'required_status_checks[contexts][]=Backend (lint, migration, tests)' \
  -f 'required_status_checks[contexts][]=Dependency scan (pip-audit)' \
  -f 'required_status_checks[contexts][]=E2E (chromium thật + PostgreSQL)' \
  -f 'required_status_checks[contexts][]=E2E (firefox thật + PostgreSQL)' \
  -f 'required_status_checks[contexts][]=E2E (webkit thật + PostgreSQL)' \
  -f 'required_status_checks[contexts][]=Secret scan (gitleaks)' \
  -f 'required_status_checks[contexts][]=Validate static frontend' \
  -f enforce_admins=false \
  -f required_pull_request_reviews[required_approving_review_count]=0 \
  -F allow_force_pushes=false \
  -F allow_deletions=false
```

**Hai lựa chọn Owner phải quyết:**

1. **`enforce_admins`** — đặt `true` thì chính Owner cũng không push thẳng được (kỷ luật chặt nhất,
   nhưng lúc khẩn cấp phải tắt protection mới sửa nhanh được). Đặt `false` thì Owner vẫn bypass được.
   Hai lệnh trên để `false`; đổi thành `-F enforce_admins=true` nếu muốn chặt.
2. **Số người duyệt PR** — hiện để `0` vì repo có một người. Nếu muốn ít nhất 1 người duyệt thì
   thêm `-f required_pull_request_reviews[required_approving_review_count]=1`
   (⚠️ khi đó **chính Owner cũng không tự merge PR của mình được** nếu không có người thứ hai).

**Kiểm lại sau khi bật:**

```bash
gh api repos/thanhbn123/vipphone/branches/main/protection --jq '{
  strict: .required_status_checks.strict,
  checks: .required_status_checks.contexts,
  force_push: .allow_force_pushes.enabled,
  deletions: .allow_deletions.enabled }'
```

---

## D-004 — CHÍNH SÁCH LƯU TRỮ PII — ✅ **CLOSED** (Owner chốt 2026-10-02)

| Loại dữ liệu | Thời hạn |
|---|---|
| Lead tiếp thị (không giao dịch) | **12 tháng** |
| Dữ liệu TEST | **xoá sau khi nghiệm thu** |
| Hồ sơ khách hàng / giao dịch | theo quy định **kế toán – thuế – kinh doanh** (quản lý riêng) |
| Bản ghi audit / kỹ thuật | **tối thiểu 12 tháng** |

**Công cụ thi hành:** `scripts/cleanup_test_data.py` — xoá theo **marker**, từ chối
`APP_ENV=production`, in số lượng TRƯỚC khi xoá. **Đã chạy thật trên staging.**

**CỐ Ý KHÔNG làm:** không xoá hàng loạt dữ liệu hiện có chỉ để chứng minh chính sách.
**Chưa có** job tự động xoá lead quá 12 tháng — việc còn lại.

---

## D-004 (bản cũ, giữ tham chiếu) — CHÍNH SÁCH LƯU TRỮ PII

**Trạng thái:** **OWNER_DECISION_REQUIRED**. Hiện **chưa quyết ⇒ dữ liệu giữ vô thời hạn**.

**Đọc:** [`decisions/PII_RETENTION_OPTIONS.md`](decisions/PII_RETENTION_OPTIONS.md) — ba phương án
**A — MINIMAL**, **B — STANDARD CRM**, **C — EXTENDED MARKETING**, kèm đánh đổi.
Tài liệu đó **không** chọn hộ phương án nào.

**Cần Owner trả lời 5 câu** (chi tiết ở cuối tài liệu phương án):

1. Chọn A, B hay C — hay biến thể (nói rõ số).
2. "Đang hoạt động" định nghĩa thế nào (chỉ áp dụng cho B).
3. Ai chịu trách nhiệm xử lý yêu cầu xoá dữ liệu của khách.
4. Có cần rà soát pháp lý không. **Tài liệu trong repo không phải lời khuyên pháp lý và không thay
   thế được việc rà soát đó.**
5. `audit_events` (`lead_id`, `gift_code`, `actor` chứa IP): xoá theo cùng mốc hay giữ lâu hơn để
   kiểm toán? Hai mục tiêu này **đối nghịch** và phải chọn.

**Vì sao cần Owner chứ không phải kỹ thuật:** đây là đánh đổi giữa **rủi ro dữ liệu** và **giá trị
kinh doanh**. Kỹ thuật chỉ dựng được cơ chế, không quyết được mức chấp nhận rủi ro.

---

## Không nằm trong danh sách này (đã xử lý hoặc không cần Owner)

| Việc | Vì sao không cần Owner |
|---|---|
| Chọn stack backend | Đã có ADR-0001 |
| Chính sách chống trùng gift | Đã chốt và có test |
| PII trong QR | Đã cấm bằng test |
| Chính sách fail-open/closed Turnstile | Đã chốt ở `docs/staging.md` §3.1 |
| Retention trong code | **Chờ D-004** — cố ý không đoán hộ |
| Deploy production | **FORBIDDEN** ở phiên này, cần release gate riêng |

---

## D-005 — RPO / RTO VÀ LỊCH SAO LƯU — ✅ **CLOSED** (Owner chốt 2026-10-02)

| Chỉ số | Giá trị Owner chốt |
|---|---|
| **RPO** | **24 giờ** |
| **RTO** | **4 giờ** |
| Tần suất | **hằng ngày** (PostgreSQL) |
| Giữ bản ngày / tuần | **14** / **4** |
| Kiểm phục hồi | **hằng tháng** |

**Công cụ:** `scripts/staging_backup.sh` — đúng chính sách, **từ chối** DB tên `*prod*`,
ghi kèm SHA-256, tự dọn theo hạn mức.

**Đối chiếu số đo với mục tiêu — NÓI THẲNG:**

| Mục tiêu | Số đo thật | Kết luận |
|---|---|---|
| RTO 4 giờ | phục hồi **0.13 giây** trên DB **1 dòng** | **KHÔNG đủ căn cứ nói đạt** — dữ liệu thật sẽ khác, chưa ai đo |
| RPO 24 giờ | chưa có lịch chạy tự động | **CHƯA ĐẠT** |

**⚠️ Giới hạn:** script lưu **cùng máy staging** ⇒ mất máy là mất cả hai. Cần đích **khác máy**.

**Đo lại 2026-10-10 (user `deploy` trên `160.22.170.20`, chỉ đọc):** `crontab -l` không có dòng nào cho vipphone/sao lưu,
không có timer systemd nào tên vipphone. Bản sao lưu tự động cuối cùng trong `~/vipphone-staging/backups/daily` là
**2026-10-03 00:13** (từ trước sự cố §35). Các bản trong `~/vip/vipphone/staging/backups/` đều do `deploy/backup.sh`
chạy tay hoặc theo lượt deploy ⇒ **RPO 24 giờ: CHƯA ĐẠT**. Bật lịch là thêm cấu hình bền trên máy chủ ⇒ **Owner quyết**:
(a) cron của user `deploy` gọi `deploy/backup.sh` qua bản phát hành `current`, hoặc (b) nối vào hệ sao lưu chung VIP Vault.

---

## D-005 (bản cũ, giữ tham chiếu) — RPO / RTO VÀ LỊCH SAO LƯU

**Trạng thái:** **OWNER_DECISION_REQUIRED**. Hiện **chưa có lịch sao lưu nào**.

**Need.** Chọn mức chịu mất dữ liệu. Toàn bộ lead, gift code và vết phát quà nằm trong **một**
PostgreSQL. Không có bản sao lưu nào **đã được kiểm** thì chưa có bản sao lưu nào.

**Đã có sẵn trong repo:** `docs/backup-restore.md` — lệnh sao lưu/phục hồi, cách kiểm, và một
`LOCAL BACKUP/RESTORE TEST` **đã chạy thật** (250 lead, kiểm bằng **md5 nội dung**, không chỉ đếm dòng).

**Khung để chọn** (KHÔNG phải khuyến nghị):

| Phương án | Tần suất | Mất tối đa | Công / chi phí |
|---|---|---|---|
| Cơ bản | mỗi ngày | tới **24 giờ** lead | thấp |
| Vừa | mỗi giờ | tới **1 giờ** | cần lịch chạy + chỗ lưu |
| Chặt | WAL liên tục (PITR) | gần như **0** | cần cấu hình archive + dung lượng lớn |

**Cần Owner trả lời:**

1. **RPO** — mất tối đa bao nhiêu dữ liệu là chấp nhận được?
2. **RTO** — phục hồi xong trong bao lâu?
3. **Giữ bao nhiêu bản**, trong bao lâu?
4. **Lưu ở đâu** — có được để **cùng máy** với database không? (khuyến nghị: **không**)
5. **Có mã hoá bản dump không?** Bản dump chứa **đầy đủ PII** và **không** được hưởng quyền bảo vệ
   của database.
6. **Ai chịu trách nhiệm** chạy sao lưu, và **ai kiểm** định kỳ? Sao lưu không được kiểm thì không
   phải sao lưu.

**Vì sao không tự chọn:** đây là **mức chấp nhận rủi ro kinh doanh**. Kỹ thuật dựng được cơ chế;
chỉ Owner biết mất một ngày lead có sao không.


---

## D-006 — ĐƯỜNG TRIỂN KHAI STAGING CHO CÁC GATE THƯƠNG MẠI — ✅ CLOSED (2026-10-10)

**Đóng 2026-10-10:** Owner chọn cách 1 (chạy từ MacBook). `bash scripts/owner_staging_run.sh` trên `develop` `85a5f06`
qua 27/27 bước sau hai bản vá chỉ lộ ra trên máy thật (#92, #95) — `MASTER_STATUS.md` §40, `OWNER_ACCEPTANCE_COMMERCE.md` §H.
Phần dưới giữ làm lịch sử.


**Đo lại 2026-10-08:** vẫn `CONNECT tunnel failed, response 403` cho `qua.viporder.vn`; TCP `160.22.170.20:22`
bị chặn; `~/.ssh` trống; không có phiên Claude nào trên máy Owner (Remote Control) để chuyển việc.
**Toàn bộ khối lệnh, theo đúng thứ tự nghiệm thu, nằm ở `docs/STAGING_RUNBOOK_COMMERCE.md`.**

**Đo được (2026-10-07) từ phiên làm việc của harness (container cloud):**

```
curl https://qua.viporder.vn/   → CONNECT tunnel failed, response 403   (proxy mạng của môi trường chặn)
ls ~/.ssh                        → trống (không có khoá SSH của host staging)
```

Hệ quả: mã G15 → attribution **đã merge vào `develop` và xanh CI 7/7**, nhưng **chưa** được deploy lên
`https://qua.viporder.vn`; `develop ≠ staging`. Không có gì bị "giả PASS" — xem `docs/OWNER_ACCEPTANCE_COMMERCE.md`.

**Chọn MỘT trong hai cách:**

1. **Chạy từ MacBook** (máy đang có khoá `vip_viettelpost_staging_*`), trên `develop` mới nhất:

   ```bash
   git fetch origin && git checkout develop && git pull --ff-only
   ./deploy/staging.sh                         # 4 cửa khoá: cây sạch · test · phiếu · băm gói
   ./deploy/verify.sh staging                  # đối chiếu băm mã trên máy chủ
   STAFF_KEY=<khoá nhân viên staging> [MOCK_SECRET=<khoá webhook giả lập>] \
     .venv/bin/python scripts/staging_commerce_smoke.py \
       --base-url https://qua.viporder.vn --i-know-this-is-staging     # 24 bước, PASS/FAIL
   # Dọn dữ liệu thử (chạy TRÊN máy chủ, trong mạng docker của staging):
   DATABASE_URL=... APP_ENV=staging python scripts/cleanup_test_data.py           # đếm
   DATABASE_URL=... APP_ENV=staging python scripts/cleanup_test_data.py --apply   # xoá
   DATABASE_URL=... python scripts/restore_drill.py                               # sao lưu → phục hồi → so md5
   ```

2. **Cho harness quyền đi tới staging**: trong cài đặt môi trường cloud, thêm `qua.viporder.vn` (và
   cổng SSH của host) vào danh sách mạng cho phép, và cấp khoá SSH deploy dưới dạng **secret** của môi
   trường (không dán vào chat). Phiên sau harness tự chạy toàn bộ khối lệnh trên.

## D-007 — `enforce_admins`

Hiện `false` ở cả hai nhánh: tài khoản admin vẫn merge được PR có check đỏ (PR thường thì bị chặn — đã đo).
`true` = kỷ luật chặt nhất nhưng sự cố khẩn cấp phải tắt protection mới sửa nhanh được. Harness **không** tự đổi.

## D-008 — BIỂU PHÍ GIAO HÀNG

Mã đã có MỘT hàm `shipping_fee_for()` dùng chung cho giỏ và checkout; hiện là phí **cố định**
`SHIPPING_FEE_FLAT` (mặc định `0.00`). Owner chốt: miễn phí / đồng giá (bao nhiêu) / theo tỉnh / theo
ngưỡng đơn. Đồng giá thì chỉ cần đặt biến môi trường; các kiểu khác cần một gate nhỏ.

## D-009 — NỘI DUNG CHUYỂN KHOẢN

`BANK_TRANSFER_INSTRUCTIONS` (≤ 500 ký tự, không phải secret) hiển thị cho khách chọn chuyển khoản, sau dòng
"Ghi nội dung chuyển khoản: <mã đơn>". Owner cung cấp số tài khoản, ngân hàng, chủ tài khoản.

## D-010 — KHO ẢNH PRODUCTION + SAO LƯU ẢNH

Staging lưu ảnh trên Docker named volume `vipphone-staging-media`. Từ 2026-10-10 `deploy/backup.sh` sao lưu cả volume
này (`media-<thời điểm>.tar.gz` + sha256, đọc lại bằng `tar -tzf` trước khi báo xong; bộ thử `thu-deploy.sh` nhóm 17). Production nên dùng kho đối tượng S3-compatible (+ CDN) — chỉ cần thêm một lớp hiện thực
`app/storage.ObjectStorage`. Owner chọn nhà cung cấp/vùng lưu trữ; chưa chọn thì production chưa có ảnh bền.

## D-011 — KHOÁ WEBHOOK GIẢ LẬP TRÊN STAGING (tuỳ chọn)

Đặt `PAYMENT_MOCK_WEBHOOK_SECRET` (chuỗi ngẫu nhiên, chỉ trong `shared/.env` của staging) để bật phương thức
`STAGING_MOCK` và chạy được phần webhook của `staging_commerce_smoke.py`. Không đặt thì phần đó ghi NOT TESTED.
**Không bao giờ** đặt ở production (mã cũng tự tắt giả lập khi `APP_ENV=production`).
