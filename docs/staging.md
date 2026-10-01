# Hợp đồng cấu hình STAGING — VIP PHONE

> Mục đích: người dựng staging chỉ cần đọc **một** tài liệu này là biết phải đặt biến gì,
> biến nào là secret, biến nào đọc lúc build, biến nào đọc lúc chạy — và **cái gì sẽ hỏng**
> nếu đặt sai.
>
> File mẫu điền nhanh: [`.env.staging.example`](../.env.staging.example)
> Kiểm tra tự động: `scripts/staging_preflight.sh`
>
> **Trạng thái:** repo-side sẵn sàng. **Staging thật = NOT DEPLOYED** (chưa có hạ tầng).

---

## 1. Phân loại

Bốn nhãn, dùng đúng nghĩa:

- **REQUIRED** — thiếu là hệ thống chạy sai hoặc không chạy. `staging_preflight.sh` sẽ **chặn**.
- **OPTIONAL** — thiếu vẫn chạy, nhưng có hành vi mặc định cần biết.
- **SECRET** — **không bao giờ** được vào repo, log, ảnh chụp màn hình, hay trình duyệt.
- **PUBLIC** — hiện ra cho khách; lộ cũng không sao.
- **BUILD-TIME** — phải có **trước khi build/đóng gói**; nhúng vào artifact.
- **RUN-TIME** — đọc lúc tiến trình khởi động; đổi thì **khởi động lại**, không cần build lại.

| Biến | REQUIRED? | SECRET? | BUILD/RUN | Giá trị staging | Mã đọc biến này |
|---|---|---|---|---|---|
| `APP_ENV` | **REQUIRED** | PUBLIC | RUN | `staging` | ✅ có |
| `LOG_LEVEL` | OPTIONAL | PUBLIC | RUN | `INFO` (đặt `WARNING` nếu log quá ồn) | ✅ có |
| `DATABASE_URL` | **REQUIRED** | **SECRET** | RUN | PostgreSQL 16 **riêng của staging** | ✅ có |
| `SQL_ECHO` | OPTIONAL | PUBLIC | RUN | `false` — **bật là log chứa dữ liệu bảng** | ✅ có |
| `PUBLIC_BASE_URL` | **REQUIRED** | PUBLIC | RUN | `https://staging.<domain>` | ✅ có |
| `STAFF_API_KEYS` | **REQUIRED** | **SECRET** | RUN | ≥1 khoá mạnh, mỗi người/quầy một khoá | ✅ có |
| `GIFT_CODE_YEAR_PREFIX` | OPTIONAL | PUBLIC | RUN | để trống = suy từ năm UTC | ✅ có |
| `GIFT_CODE_LENGTH` | OPTIONAL | PUBLIC | RUN | `6` | ✅ có |
| `GIFT_CODE_MAX_ATTEMPTS` | OPTIONAL | PUBLIC | RUN | `8` | ✅ có |
| `RATE_LIMIT_ENABLED` | OPTIONAL | PUBLIC | RUN | `true` | ✅ có |
| `RATE_LIMIT_LEADS_PER_WINDOW` | OPTIONAL | PUBLIC | RUN | `10` | ✅ có |
| `RATE_LIMIT_WINDOW_SECONDS` | OPTIONAL | PUBLIC | RUN | `60` | ✅ có |
| `TRUST_PROXY_HEADERS` | OPTIONAL | PUBLIC | RUN | `true` **chỉ khi** proxy ghi đè `X-Forwarded-For` | ✅ có |
| `ALLOWED_HOSTS` | **REQUIRED** | PUBLIC | RUN | `staging.<domain>` | ✅ có |
| `TURNSTILE_SECRET_KEY` | OPTIONAL | **SECRET** | RUN | khoá Cloudflare; trống = tắt | ✅ có |
| `TURNSTILE_SITE_KEY` | OPTIONAL | **PUBLIC** | RUN | khoá site; **lộ được, là khoá công khai** | ✅ có |
| `TURNSTILE_REQUIRED` | OPTIONAL | PUBLIC | RUN | `false` cho tới khi widget có mặt | ✅ có |
| `MAX_LEAD_BODY_BYTES` | OPTIONAL | PUBLIC | RUN | `8192` | ✅ có |
| `EXPOSE_READINESS_DETAILS` | OPTIONAL | PUBLIC | RUN | `false` ở staging | ✅ có |

**BUILD-TIME: không có biến nào.** Frontend là HTML/CSS/JS tĩnh **không có bước build**, nên toàn
bộ cấu hình là **RUN-TIME**. Đây là hệ quả trực tiếp của ADR-0001 §3.2 (một tiến trình phục vụ
cả API lẫn file tĩnh), không phải thiếu sót.

---

## 2. Hai biến KHÔNG tồn tại — và vì sao

### 2.1 `SECRET_KEY` / session signing secret — **KHÔNG CẦN**

Stack này **không có phiên, không có cookie**. Xác thực nhân viên là **khoá API gửi qua header**
(`X-Staff-Key` hoặc `Authorization: Bearer`), so bằng `secrets.compare_digest`. **Không có gì để ký.**

Ghi ra đây để người dựng staging không đi tìm một biến không tồn tại, và để không ai "bổ sung cho
đủ danh sách" rồi tạo ra một secret thừa không ai dùng.

> Nếu sau này thêm phiên cookie thì **PHẢI** thêm secret ký, và phải ghi vào bảng trên **trước khi** merge.

### 2.2 `CORS_ALLOWED_ORIGINS` — **ĐÃ GỠ, CỐ Ý**

API và frontend phục vụ **cùng origin** nên CORS không cần. Trước đây biến này **tồn tại mà không
middleware nào đọc** — cấu hình an ninh đọc như đã làm mà thực ra chưa làm, tệ hơn cả không có.
Đã gỡ ở G08 và có test khẳng định **không** rò header CORS cho origin lạ.
Nếu sau này tách frontend sang origin khác thì gắn `CORSMiddleware` với allowlist **tường minh**
(không `*`) **và viết test**.

---

## 3. Turnstile — cách bật, và cái bẫy đã được chặn

**Đường đi đã nối đủ** (SR-2):

```
server: TURNSTILE_SITE_KEY + TURNSTILE_SECRET_KEY
   -> GET /api/public-config   (công khai: enabled + site_key, KHÔNG có secret)
   -> assets/js/turnstile.js   (nạp script Cloudflare + render widget)
   -> khách giải challenge     -> turnstile_token gửi kèm POST /api/leads
   -> server xác minh tại /siteverify  (verify_turnstile)
```

**Cái bẫy — và cách nó bị chặn.** Trước SR-2, bật `TURNSTILE_REQUIRED=true` khi frontend **chưa có
widget** sẽ **chặn mọi lead** (403) mà không ai hiểu vì sao. Nay:

- `/api/public-config` trả `enabled = false` khi **thiếu một trong hai khoá**, kèm `warning` nói rõ.
- `turnstile.js` chỉ nạp script Cloudflare khi `enabled = true`; tắt thì **không nạp gì từ Internet**
  (có test E2E bắt request trình duyệt thật để chứng minh).
- CSP **chỉ** mở cho `challenges.cloudflare.com` khi Turnstile bật; tắt thì CSP quay về
  `script-src 'self'`.
- Frontend chặn gửi và nói rõ khi bật mà chưa có token, thay vì để khách nhận lỗi khó hiểu.

**Vẫn phải giữ `TURNSTILE_REQUIRED=false` cho tới khi có khoá thật.** Chưa có khoá ⇒ bot protection
đang **TẮT**, và `/api/ready` báo `NOT_CONFIGURED` để điều đó không bị bỏ quên.

**Khoá SECRET không bao giờ ra phía client** — có test khẳng định `/api/public-config` không chứa
secret, và CI có chốt chặn grep `TURNSTILE_SECRET_KEY` trong `assets/` + `*.html` (kèm đối chứng dương).

### 3.1 Chính sách fail-open / fail-closed

| Môi trường | `TURNSTILE_REQUIRED` | Có secret? | Hành vi |
|---|---|---|---|
| `dev` | `false` | không | **Bỏ qua** kiểm tra |
| `test` | `false` | không | **Bỏ qua** — test dùng verifier giả |
| `staging` | `false` (khuyến nghị) | không | **Bỏ qua**, và `/api/ready` báo `NOT_CONFIGURED` để **không im lặng** |
| `staging`/`production` | `true` | **có** | Thiếu token → **403**; Cloudflare lỗi/timeout → **503** (không nuốt lỗi) |
| `staging`/`production` | `true` | **không** | **Từ chối mọi yêu cầu** — cấu hình nửa vời bị chặn, **không** âm thầm bỏ qua |

Luật: **khi đã yêu cầu thì fail CLOSED.** Chưa cấu hình thì nói thẳng ra (readiness báo
`NOT_CONFIGURED`), chứ **không** giả vờ đang bảo vệ.

---

## 4. Bốn biến dễ đặt sai nhất

| Biến | Đặt sai thì hỏng thế nào |
|---|---|
| `PUBLIC_BASE_URL` | Là địa chỉ **nhúng vào mã QR**. Sai ⇒ QR in ra trỏ vào `localhost`, khách quét không được, và **chỉ lộ ra khi đã in** |
| `ALLOWED_HOSTS` | Để rỗng ⇒ **không giới hạn Host** ⇒ host-header injection. Ở production, máy chủ **ghi cảnh báo** và readiness báo `NOT_CONFIGURED` |
| `TRUST_PROXY_HEADERS` | Bật khi proxy **không** ghi đè `X-Forwarded-For` ⇒ client tự đặt header và **né rate limit**. Tắt khi proxy **có** ghi đè ⇒ mọi request cùng một IP ⇒ rate limit chặn nhầm cả tòa nhà |
| `DATABASE_URL` | Trỏ nhầm vào database **production** ⇒ staging ghi vào dữ liệu thật. Preflight **chặn** nếu tên database không trông giống staging |

---

## 5. Kiểm tra trước khi deploy

```bash
APP_ENV=staging PUBLIC_BASE_URL=https://staging.<domain> \
DATABASE_URL=... STAFF_API_KEYS=... ALLOWED_HOSTS=staging.<domain> \
  scripts/staging_preflight.sh
```

Script **thoát mã khác 0** nếu thiếu biến bắt buộc, database không nối được, migration chưa ở
head, health/ready không đạt, hoặc cấu hình Turnstile mâu thuẫn. Xem `docs/deployment.md`.
