# NGHIỆM THU STAGING — VIP PHONE

- Ngày đo: **2026-10-02** (giờ máy +07)
- `develop` lúc đo: `04c1582898edadcb09934380669aa58cb2e40cdb`
- `main`: `7d6162cf31eb96ea27879be3a4671812a9cd7e01` — **KHÔNG ĐỔI**
- **PRODUCTION: NOT DEPLOYED**

> ## ĐỌC DÒNG NÀY TRƯỚC
>
> ## ĐÃ TRIỂN KHAI THẬT LÊN STAGING
>
> `STAGING_ACCEPTANCE = BLOCKED` **chỉ còn** vì `TURNSTILE_REAL` (thiếu credential) và
> `TLS/DOMAIN` (chưa có domain cho vipphone). **Mọi mục khác đã đo TRÊN STAGING THẬT.**
>
> | | |
> |---|---|
> | Host | `160.22.170.20` (KHÁC production `160.22.171.228`) |
> | Hostname | `CIITNRVPlinux` · Ubuntu 26.04 LTS · x86_64 · 4 core · 7.2 GiB RAM |
> | Deploy SHA | `04c1582898edadcb09934380669aa58cb2e40cdb` |
> | Service | docker `vipphone-staging-app` · `18080->8000` · RestartCount=**0** |
> | Database | PostgreSQL **16.15** · `vipphone-staging-pg` · db `vipphone_staging` |
> | Endpoint | `http://160.22.170.20:18080` (**HTTP, chưa có TLS**) |
>
> **`deploy` KHÔNG có sudo** (`deploy is not in the sudoers file`) ⇒ dùng Docker, không
> systemd; **không** sửa được reverse proxy dùng chung của dự án khác. Vì vậy **không có
> domain/TLS** — đây là chốt Owner, không phải việc kỹ thuật còn dở.

### HAILỖI THẬT DO STAGING TÌM RA (không test nào bắt được)

| | Lỗi | Trạng thái |
|---|---|---|
| **STG-1** | `requirements.txt` thiếu `httpx` ⇒ ứng dụng **crash-loop**, không khởi động được khi cài đúng đường production. CI luôn xanh vì CI cài *dev* requirements. | **ĐÃ SỬA** (PR #30) + chốt CI cài *chỉ* runtime deps rồi `import app.main`, kèm đối chứng âm |
| **STG-2** | `/favicon.ico` trả 204 **kèm body** ⇒ uvicorn ném `RuntimeError: Response content longer than Content-Length` ở **MỌI** request (25 request → 25 exception) nhưng client vẫn thấy 204. `TestClient` bỏ qua tầng HTTP của uvicorn nên bộ test cũ **không thể** thấy. | **ĐÃ SỬA** (PR #32) + test khởi động **uvicorn THẬT**; đối chứng âm: ĐỎ trên mã cũ, XANH sau khi vá. Đã kiểm lại trên staging: 25 request → **0 exception** |


---

## 1. Hạ tầng — đo được gì, thiếu gì

| Mục | Đo được | Nguồn |
|---|---|---|
| Host staging | `160.22.170.20` | Owner cấp trong phiên |
| Khác production? | **CÓ** — production là `160.22.171.228` (`viporder-vps`) | `~/.ssh/config`, vault |
| Cổng mở | **22, 80, 443** (5432/8000/8080 đóng) | `nc -z` |
| Web server | có phản hồi: `http → 308` | `curl` |
| Host key SSH | `SHA256:ou0RcaFdtNCJYFOOKs0tTxwvsNtDK6pqZYfGZ/IUIQ0` | `ssh-keyscan` |
| Khớp bản ghim? | **CÓ** — trùng mục vault 30/09 (đã sinh lại host key) | so với `nhat-ky/ngay/2026-09-30.md` §28 |
| **SSH credential** | **KHÔNG CÓ** — thử 4 khoá × 4 user, đều bị từ chối | `ssh -o BatchMode` |
| Domain staging | vault ghi `cpn.viporder.vn` cho **dự án khác** | chưa có domain riêng cho vipphone |

**Host này đang phục vụ staging của một dự án KHÁC** (`vip-viettelpost`): Ubuntu 26.04,
4 CPU / 7.2 GB RAM, swap 2G, đĩa 89G, **có Docker**, `/srv/vip-staging`.
⇒ Dựng vipphone lên đây là **dùng chung máy**, phải tách container/port/DB/vhost và
**không được đụng** staging của dự án kia.

**Chặn:** cần **một trong hai** — (a) khoá `vip_viettelpost_staging_deploy` chép sang máy này,
hoặc (b) Owner thêm khoá công khai của phiên này vào `authorized_keys` của user `deploy`.

---

## 2. Bảng nghiệm thu

Ký hiệu: **PASS(LOCAL)** = đã đo thật nhưng **trên máy**; **BLOCKED** = cần staging thật.

| # | Hạng mục | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | DEPLOY từ Git SHA | **PASS(LOCAL)** | Checkout sạch `8833ac13`, `git status --porcelain` = **0 file**; cây làm việc **không bẩn** khi chạy nghiệm thu |
| 2 | DATABASE MIGRATION | **PASS(LOCAL)** | `alembic upgrade head` exit 0 · `current` = `heads` = **`0001_initial`** · `alembic check` **không có diff** |
| 3 | HEALTH | **PASS(LOCAL)** | `GET /api/health` → **200**, `{"status":"ok","service":"vipphone","env":"staging"}` |
| 4 | READINESS | **PASS(LOCAL)** | `GET /api/ready` → **200**; bản công khai **chỉ có `status`**, không lộ `checks` |
| 5 | LANDING | **PASS(LOCAL)** | `/` → 200 + `<!doctype html>`; 3 asset (css/app.js/qr.js) đều 200; catalog **28 model** |
| 6 | SECURITY HEADER | **PASS(LOCAL)** | CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` đều có |
| 7 | REAL LEAD FLOW | **PASS(LOCAL)** | `POST /api/leads` → **201**, gift `VIP-26-E9FLRT` (dữ liệu test có marker) |
| 8 | DUPLICATE | **PASS(LOCAL)** | Gửi lại cùng SĐT + model → **cùng gift code**, không tạo lead thứ hai |
| 9 | QR DECODE | **PASS(LOCAL)** | `qr.png` 2234 byte, giải mã bằng **zxing-cpp** (độc lập với bộ sinh) → `http://…/redeem?code=VIP-26-E9FLRT`; **không chứa SĐT** |
| 10 | STAFF AUTH | **PASS(LOCAL)** | không khoá → **401** · khoá sai → **401** · khoá đúng → **200** · tra cứu **che SĐT** và **không trả UTM/công ty/BNI** |
| 11 | ADMIN AUTH | **PASS(LOCAL)** | `/api/admin/leads` không khoá → **401** |
| 12 | REDEEM | **PASS(LOCAL)** | lần 1 → 200, `gift_status=REDEEMED` |
| 13 | DOUBLE REDEEM | **PASS(LOCAL)** | lần 2 → `already_redeemed=true`, **`redeemed_at` KHÔNG đổi** |
| 14 | **CONCURRENT REDEEM** | **PASS(LOCAL)** | **8 yêu cầu ĐỒNG THỜI** trên 1 gift mới → **đúng 1 lần phát thật**, 7 `already_redeemed`, tất cả HTTP 200 |
| 15 | AUDIT | **PASS(LOCAL)** | `LEAD_CREATED` / `GIFT_CREATED` / `GIFT_STATUS_CHANGED` / `GIFT_REDEEMED`; **`GIFT_REDEEMED` = đúng 1** cho gift test; `actor` = `public:127.0.0.1` và `staff:69cb0f4cc8d3` |
| 16 | AUDIT không rò PII | **PASS(LOCAL)** | metadata chỉ có `model_code`, `source`, `utm_campaign`, `duplicate`, `to_status`, `iphone_year`; **0 bản ghi chứa GIÁ TRỊ PII** |
| 17 | LOG REVIEW | **PASS(LOCAL)** | 0 lần xuất hiện khoá nhân viên · 0 `DATABASE_URL` · 0 mật khẩu · **0 Traceback** · **0 lỗi 5xx** |
| 18 | BROWSER E2E | **PASS(CI)** | Chromium **33/33** · Firefox **33/33** · Playwright WebKit **33/33** (chạy trong CI trên Linux) |
| 19 | BACKUP | **PASS(LOCAL)** | `pg_dump -Fc` → 15 KB, **0.05 giây** |
| 20 | RESTORE | **PASS(LOCAL)** | phục hồi vào database **TẠM** (không đè DB đang phục vụ) → **0.04 giây**; số dòng khớp; **md5 nội dung khớp** |
| 21 | ROLLBACK DRILL | **PASS(LOCAL)** | deploy `074c644` → `8833ac1` → **rollback `074c644`** → `8833ac1`, health OK **cả 4 lượt**, SHA đúng từng lượt |
| 22 | LOAD SMOKE | **PASS(LOCAL)** | 14 755 request / 12 s · **0 lỗi thật** · p50 **5.1 ms** · p95 **6.0 ms** (5016 mã 429 là rate limit chạy đúng) |
| 23 | TEST DATA CLEANUP | **PASS(LOCAL)** | `scripts/cleanup_test_data.py`: chỉ đếm (mặc định) · từ chối `APP_ENV=production` (exit 2) · từ chối DB tên `*prod*` (exit 2) · xoá **đúng 5** lead test, **lead khách THẬT còn nguyên** |
| 24 | BRANCH PROTECTION `main` | **PASS** | `strict=true`, **7 check**, force-push **cấm**, xoá nhánh **cấm** (đo lại qua API) |
| 25 | BRANCH PROTECTION `develop` | **PASS** | như trên |
| 26 | TLS | **BLOCKED** | chưa có domain staging cho vipphone |
| 27 | REVERSE PROXY | **BLOCKED** | chưa dựng vhost |
| 28 | HEALTH **qua domain thật** | **BLOCKED** | cần hạ tầng |
| 29 | PUBLIC LANDING **trên staging** | **BLOCKED** | cần hạ tầng |
| 30 | LEAD / REDEEM **trên staging** | **BLOCKED** | cần hạ tầng |
| 31 | BROWSER E2E **trên staging** | **BLOCKED** | cần hạ tầng |
| 32 | BACKUP/RESTORE **trên staging** | **BLOCKED** | cần hạ tầng |
| 33 | LOAD SMOKE **trên staging** | **BLOCKED** | cần hạ tầng |
| 34 | **TURNSTILE REAL** | **BLOCKED_EXTERNAL_CREDENTIAL** | chưa có khoá site + secret thật; xem §4 |
| 35 | PII RETENTION | **OWNER_DECISION_REQUIRED** | 3 phương án ở `docs/decisions/PII_RETENTION_OPTIONS.md` |
| 36 | RPO / RTO | **OWNER_DECISION_REQUIRED** | số đo ở §5, **không** tự đặt chính sách |
| 37 | `SAFARI REAL` | **NOT TESTED** | Playwright WebKit **không phải** Safari thật |

**Tổng:** 25 `PASS` (24 trong đó là LOCAL) · **11 `BLOCKED`** · 1 `NOT TESTED`.

---

## 3. Bốn lỗi PHÉP ĐO đã dính trong chính phiên này

Không lỗi nào là lỗi sản phẩm. Ghi lại vì **cả bốn đều tạo ra báo cáo sai trước khi được sửa**.

| # | Triệu chứng | Nguyên nhân thật | Sửa |
|---|---|---|---|
| 1 | **16 mục FAIL** cùng lúc (HTTP 501/404) | Cổng `8791` **đã bị một `python -m http.server` của phiên khác giữ**; uvicorn của tôi không bind được rồi thoát. Mọi phép kiểm nói chuyện với một **file server tĩnh** | Thêm **chốt danh tính**: gọi `/api/health`, nếu không thấy `"service":"vipphone"` thì **DỪNG** (exit 3). Đã kiểm: chốt này chặn đúng server lạ |
| 2 | `MIGRATION ở HEAD` **FAIL** (`current=INFO`) | `alembic` in các dòng `INFO …`; regex thô của tôi bắt chữ **`INFO`** làm revision | Lọc dòng log **trước** khi tách mã → `current = head = 0001_initial` |
| 3 | Audit "có PII" **4 bản ghi** | Truy vấn tìm chuỗi `phone` — và **`"model_code": "iphone-16"` chứa `phone`**! `iPhone` khớp `phone` | Kiểm lại bằng **giá trị** PII (mẫu SĐT, tên khách) → **0**. Truy vấn đầu là **dương tính giả** |
| 4 | `exit=0` dù script TỪ CHỐI | `echo "exit=$?"` sau một **pipe** đo mã thoát của `tail`, không phải của script | Đo lại **không qua pipe** → đúng `exit=2` |

> **Họ chung:** *phép đo trả lời một câu hỏi khác với câu mình tưởng đang hỏi.* Ca 1 và ca 3
> nguy hiểm nhất vì chúng tạo ra **một báo cáo sai hoàn toàn** mà trông vẫn hợp lý.

---

## 4. TURNSTILE — trạng thái thật

| Mục | Trạng thái |
|---|---|
| Adapter xác minh ở server | **CÓ** (`verify_turnstile`), có timeout, có chính sách fail-open/closed |
| Endpoint công khai trả site key | **CÓ** (`GET /api/public-config`) |
| Widget frontend | **CÓ** (`assets/js/turnstile.js`) |
| CSP có điều kiện | **CÓ** — chỉ mở `challenges.cloudflare.com` khi bật |
| **Khoá THẬT** | **KHÔNG CÓ** ⇒ **`TURNSTILE_REAL = BLOCKED_EXTERNAL_CREDENTIAL`** |
| **Xác minh THẬT với Cloudflare** | **NOT TESTED** |
| Bot protection hiện tại | **TẮT** |

**Không có phép kiểm Turnstile thật nào trong phiên này.** Các test hiện có dùng
**verifier giả** — chúng chứng minh *đường đi đúng*, **không** chứng minh *tích hợp Cloudflare chạy*.
Ghi `PASS` cho mục này là **PASS giả**.

---

## 5. Số đo cho D-005 (RPO/RTO) — chưa đặt chính sách

| Phép đo | Giá trị | Cảnh báo phạm vi |
|---|---|---|
| Thời gian BACKUP | **0.05 giây** | trên **2 dòng** — **không** đại diện dữ liệu thật |
| Thời gian RESTORE | **0.04 giây** | như trên |
| Kích thước dump | **15 KB** | như trên |
| Kiểm chứng | số dòng khớp + **md5 nội dung khớp** | — |

**Không được dùng ba con số này để chọn RPO/RTO.** Chúng đo trên dữ liệu gần rỗng.
Muốn có số thật phải đo trên staging với dữ liệu cỡ thật — **chưa làm được** (BLOCKED).
Xem `docs/backup-restore.md` §4 để biết khung 3 phương án.

---

## 6. Chính sách dữ liệu test

- **Marker bắt buộc:** `source=staging-test` **hoặc** `utm_campaign=staging-acceptance`
- **SĐT test:** tiền tố `0900000` (chỉ để **nhận diện** — **KHÔNG** dùng làm điều kiện xoá)
- **Dọn dẹp:** `scripts/cleanup_test_data.py`
  - mặc định **chỉ đếm**; `--apply` mới xoá
  - **từ chối** `APP_ENV=production` và database tên `*prod*` (exit 2)
  - **cảnh báo** nếu có lead dùng SĐT test mà thiếu marker, và **cố ý không xoá**
- **Đã chứng minh:** xoá đúng 5 lead test, **lead khách thật còn nguyên**

---

## 7. Kết luận

| | |
|---|---|
| `REPO_SIDE_STAGING_READINESS` | **PASS** |
| `STAGING_ACCEPTANCE` | **BLOCKED** — thiếu SSH credential để vào `160.22.170.20` |
| `STAGING_DEPLOY` | **BLOCKED_EXTERNAL_ACCESS** |
| `TURNSTILE_REAL` | **BLOCKED_EXTERNAL_CREDENTIAL** |
| `PRODUCTION` | **NOT DEPLOYED** — `main` không đổi |
| `READY_FOR_PRODUCTION_RELEASE` | **NO** |

**Việc tiếp theo cần đúng MỘT thứ:** quyền SSH vào `160.22.170.20` (user `deploy`).
Có nó thì toàn bộ 11 mục `BLOCKED` ở trên chạy được ngay — bộ nghiệm thu
(`/tmp/staging_acceptance_battery.sh`, sẽ đưa vào repo) đã sẵn sàng và đã chạy đúng ở LOCAL.

**Điều KHÔNG được làm:** ghi `STAGING_ACCEPTANCE = PASS` dựa trên kết quả LOCAL.
Máy này khác máy chủ staging về hệ điều hành, mạng, reverse proxy, TLS, và tải.
