# Quyết định cần OWNER — VIP PHONE

> Chỉ chứa những việc **thật sự** cần Owner: cần hạ tầng, cần credential, cần quyền quyết định
> chính sách, hoặc cần thao tác trên kênh thật. **Không** nhét quyết định kỹ thuật nhỏ vào đây.
>
> Đo ngày **2026-10-01** trên `develop` = `f79834fcd36778994a62248747ff3cc114d4e88b`.
> Mọi thứ repo-side đã xong và **không** chờ các mục dưới đây.

| # | Quyết định | Trạng thái | Chặn cái gì |
|---|---|---|---|
| D-001 | Hạ tầng staging | **MÁY CHỦ: XONG** · **TÊN MIỀN: OWNER_ACTION_REQUIRED** | HTTPS staging |
| D-002 | Credential Turnstile | **BLOCKED_EXTERNAL_CREDENTIAL** | bot protection thật |
| D-003 | Branch protection | **OWNER_ACTION_REQUIRED** | chống push thẳng `main` |
| D-004 | Chính sách lưu trữ PII | **CLOSED** — Owner đã chốt 2026-10-02 | — |
| D-005 | RPO/RTO + lịch sao lưu | **CLOSED** — Owner đã chốt 2026-10-02 | — |

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

## D-003 — BRANCH PROTECTION

**Trạng thái đo được ngày 2026-10-01:**

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
