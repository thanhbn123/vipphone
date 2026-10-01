# Triển khai VIP PHONE

> **Trạng thái thật:** repo này **CHƯA được triển khai ở đâu cả**.
> Staging = **NOT DEPLOYED**. Production = **NOT DEPLOYED**.
> Tài liệu này mô tả **cách triển khai**, không phải thông báo đã triển khai.
> Xem `docs/MASTER_STATUS.md` §16 để biết trạng thái đang đúng.

---

## 1. Kiến trúc triển khai

**MỘT tiến trình** phục vụ cả API lẫn file tĩnh, cộng **MỘT** PostgreSQL.

```
        Internet
           │
      ┌────▼─────┐
      │ reverse  │   TLS, nén, giới hạn kích thước request
      │  proxy   │
      └────┬─────┘
           │  http (nội bộ)
      ┌────▼──────────────┐
      │ uvicorn           │   app.main:app  — API + HTML/CSS/JS tĩnh
      │ (1 tiến trình)    │
      └────┬──────────────┘
           │  psycopg3
      ┌────▼──────────────┐
      │ PostgreSQL 16     │   schema do Alembic quản lý
      └───────────────────┘
```

Vì sao một tiến trình: deploy ít bước, rollback là trỏ lại phiên bản trước, không có
hai artifact lệch phiên bản với nhau. Xem `docs/adr/0001-stack-selection.md` §3.2.

---

## 2. Yêu cầu

| Thành phần | Phiên bản | Ghi chú |
|---|---|---|
| Python | **3.12** | CI và máy phát triển dùng đúng bản này |
| PostgreSQL | **16** | CI dùng `postgres:16` service container |
| Reverse proxy | bất kỳ | nginx/Caddy/Traefik — phải có TLS |

Hệ điều hành: đã đo trên macOS (máy phát triển). **Chưa đo trên Linux** — nếu triển khai
trên Linux thì đó là lần chạy đầu, phải nghiệm thu lại chứ đừng coi là đã biết chạy.

---

## 3. Biến môi trường

Sao chép `.env.example` thành `.env` rồi điền. `.env` **đã được `.gitignore`** —
**KHÔNG BAO GIỜ** commit secret.

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `APP_ENV` | có | `dev` | `dev` / `test` / `staging` / `production`. Ở `production`: **tắt** `/docs`, `/redoc`, `/openapi.json` |
| `DATABASE_URL` | có | — | `postgresql+psycopg://<user>:<password>@<host>:<port>/<db>` |
| `PUBLIC_BASE_URL` | có | `http://localhost:8000` | Dùng để dựng URL trong **mã QR**. **KHÔNG hard-code domain trong mã nguồn** |
| `STAFF_API_KEYS` | có | rỗng | Khoá nhân viên, phân tách bằng dấu phẩy. **Rỗng ⇒ khu vực nhân viên ĐÓNG (503)** |
| `GIFT_CODE_YEAR_PREFIX` | không | suy từ năm UTC | Ghim tiền tố năm của gift code |
| `GIFT_CODE_LENGTH` | không | `6` | Độ dài thân mã |
| `GIFT_CODE_MAX_ATTEMPTS` | không | `8` | Số lần thử lại khi đụng độ mã |
| `RATE_LIMIT_ENABLED` | không | `true` | |
| `RATE_LIMIT_LEADS_PER_WINDOW` | không | `10` | Số lead cho mỗi IP mỗi cửa sổ |
| `RATE_LIMIT_WINDOW_SECONDS` | không | `60` | |
| `TRUST_PROXY_HEADERS` | không | `false` | **CHỈ bật khi máy chủ THẬT SỰ nằm sau reverse proxy tin cậy.** Bật sai chỗ ⇒ kẻ tấn công giả `X-Forwarded-For` để né rate limit |
| `TURNSTILE_SECRET_KEY` | không | rỗng | Rỗng = tắt kiểm tra chống spam |
| `TURNSTILE_REQUIRED` | không | `false` | `true` mà chưa có secret ⇒ **từ chối** (không hở im lặng) |
| `LOG_LEVEL` | không | `INFO` | `WARNING` cho production |
| `ALLOWED_HOSTS` | **có ở production** | rỗng | Danh sách Host được phép, phân tách bằng dấu phẩy. **Rỗng = KHÔNG giới hạn Host** ⇒ nguy cơ host-header injection. Khi rỗng ở production, máy chủ **ghi cảnh báo lúc khởi động** và `/api/ready` báo `NOT_CONFIGURED` |
| `EXPOSE_READINESS_DETAILS` | không | `false` | Có công khai chi tiết `/api/ready` (migration head, turnstile, staff auth) cho người **không** có khoá nhân viên hay không. Chi tiết đó là **thông tin trinh sát** — chỉ bật khi có lý do |
| `SQL_ECHO` | không | `false` | In mọi câu SQL ra log. **Chỉ bật khi gỡ lỗi** — log sẽ chứa dữ liệu bảng |
| `GIFT_CODE_ALPHABET` | không | 32 ký tự | Bỏ `I`, `O`, `0`, `1` để không đọc nhầm. Phải có ≥16 ký tự khác nhau |
| `RATE_LIMIT_MAX_KEYS` | không | `10000` | Trần số khoá IP giữ trong bộ nhớ; vượt thì bỏ khoá lâu nhất |
| `TURNSTILE_VERIFY_URL` | không | endpoint Cloudflare | Chỉ đổi khi viết test |
| `MAX_LEAD_BODY_BYTES` | không | `8192` | Trần body của `POST /api/leads`. ⚠️ Hiện **kiểm SAU khi đã đọc hết body** (MASTER_STATUS §13.2 / G08-F1) |
| `STATIC_DIR` | không | gốc repo | Thư mục chứa `index.html`, `assets/`, `data/` |
| `CORS_ALLOWED_ORIGINS` | không | rỗng | ⚠️ **Hiện là cấu hình CHẾT** — chưa có `CORSMiddleware` nào dùng nó. G08 sẽ gắn hoặc xoá |

### 3.1 Sinh khoá nhân viên

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Mỗi nhân viên (hoặc mỗi thiết bị tại quầy) nên có khoá riêng: audit ghi
`staff:<12 ký tự đầu SHA-256 của khoá>`, nên khoá riêng cho phép biết **ai** đã phát quà
mà không lộ khoá.

---

## 4. Cài đặt

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Chạy thật **không** cần `requirements-dev.txt` (test, lint, Playwright).

---

## 5. Migration

Schema **chỉ** do Alembic tạo. Ứng dụng **không** gọi `create_all()`.

```bash
export DATABASE_URL='postgresql+psycopg://...'

alembic current          # đang ở revision nào
alembic upgrade head     # áp dụng migration
alembic check            # mã và migration có khớp nhau không (bắt model sửa mà quên migration)
```

**Rollback migration:**

```bash
alembic downgrade -1     # lùi MỘT bước
alembic downgrade base   # lùi về rỗng (XOÁ DỮ LIỆU — chỉ dùng ở môi trường tạm)
```

> ⚠️ `downgrade` **mất dữ liệu** ở các bảng bị bỏ. Với production, rollback schema chỉ là
> phương án cuối; ưu tiên rollback **ứng dụng** trước.

---

## 6. Chạy

```bash
.venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 \
  --workers 1 \
  --log-level info
```

### 6.1 ⚠️ `--workers` và rate limit

Rate limit nằm **trong bộ nhớ tiến trình**. Với `--workers N`, giới hạn thực tế =
`RATE_LIMIT_LEADS_PER_WINDOW × N`, vì mỗi tiến trình đếm riêng.

- Chạy **1 worker** nếu cần giới hạn chính xác.
- Muốn scale ngang mà vẫn chính xác thì phải chuyển bộ đếm sang **Redis** (chưa làm).
- **Không** được nói "đã có rate limit" mà bỏ qua phạm vi này.

### 6.2 systemd (mẫu)

```ini
[Unit]
Description=VIP PHONE API
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=vipphone
WorkingDirectory=/srv/vipphone
EnvironmentFile=/srv/vipphone/.env
ExecStart=/srv/vipphone/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=3
# Siết quyền
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/srv/vipphone

[Install]
WantedBy=multi-user.target
```

> `ProtectSystem=strict` chỉ cho ghi trong `ReadWritePaths`. Ứng dụng **không** cần ghi file
> (không có upload, log ra stdout) nên siết được như vậy.

### 6.3 Reverse proxy (mẫu nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name vipphone.example;

    # Chặn body lớn NGAY Ở PROXY, trước khi tới ứng dụng.
    # Ứng dụng cũng có trần riêng (MAX_LEAD_BODY_BYTES) nhưng proxy chặn sớm hơn.
    client_max_body_size 64k;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Khi đứng sau proxy: đặt `TRUST_PROXY_HEADERS=true` **chỉ khi** proxy là của mình và
đã ghi đè `X-Forwarded-For` như mẫu trên. Nếu không, để `false`.

---

## 7. Kiểm tra sức khoẻ

| Endpoint | Dùng cho | Truy vấn database |
|---|---|---|
| `GET /api/health` | liveness probe | **không** |
| `GET /api/ready` | readiness probe, trước khi nhận traffic | **có** (`SELECT 1` + đọc `alembic_version`) |

- `ready` trả **200** khi sẵn sàng, **503** khi chưa (database không nối được).
- **Không** dùng `/api/ready` làm liveness: nó truy vấn database nên database chậm sẽ
  làm orchestrator giết tiến trình đang khoẻ.

---

## 8. Quy trình phát hành (đề xuất)

1. `main` đã được Owner cho phép release (xem §10).
2. Build artifact/tag từ đúng SHA đã qua CI.
3. **Sao lưu database** trước khi migrate.
4. `alembic upgrade head`.
5. Khởi động lại tiến trình.
6. Nghiệm thu: `GET /api/health` = 200, `GET /api/ready` = 200 và `checks.database = "ok"`,
   `checks.migration_head` đúng revision vừa áp.
7. Thử một lead thật trên staging, kiểm QR giải mã được, kiểm phát quà.

**Rollback:** trỏ lại artifact trước. Nếu migration không tương thích ngược thì
`alembic downgrade` về revision trước **trước khi** trỏ lại artifact.

---

## 9. Việc còn thiếu trước khi coi là sẵn sàng production

Ghi thẳng, không tô hồng:

- [ ] **Hạ tầng staging thật** — `BLOCKED_EXTERNAL_INFRA`, cần Owner cấp máy + tên miền
- [ ] **TLS** — chưa có chứng chỉ nào
- [ ] **Quản lý secret** — hiện dùng file `.env`; nên chuyển sang secret manager
- [ ] **Sao lưu database** — chưa có lịch, chưa có bản thử phục hồi
- [ ] **Giám sát / cảnh báo** — chưa có
- [ ] **Thu thập log tập trung** — chưa có
- [ ] **Rate limit nhiều instance** — cần Redis nếu chạy nhiều worker
- [ ] **Turnstile/reCAPTCHA** — mới có adapter, **chưa có khoá thật** ⇒ bot protection đang **TẮT**
- [ ] **GTM/GA4/Meta Pixel** — mới có `window.dataLayer`, chưa nối đích
- [ ] **Chính sách lưu trữ PII** — chưa quy định thời hạn lưu lead và log IP
- [ ] **Bảo vệ nhánh `main`** — repo hiện **chưa** bật branch protection (cần Owner)
- [ ] **Đo trên Linux** — mọi phép đo tới nay chạy trên macOS; lần chạy đầu trên Linux phải coi là **chưa biết**
- [ ] **Đo tải đồng thời** — chưa làm
- [ ] **Trình duyệt khác** — E2E mới chạy trên Chromium, chưa thử Firefox/Safari thật

---

## 10. Luật release

- **KHÔNG** triển khai production khi chưa có lệnh release **riêng** của Owner.
- **KHÔNG** merge `main` để release nếu chưa có lệnh đó.
- **KHÔNG** SSH vào máy chủ để sửa mã nguồn trực tiếp.
- **KHÔNG** sửa nginx/database production bằng tay.
- Mọi thay đổi đi theo: issue → branch → code → test → PR → **CI xanh** → merge `develop`.

---

## 11. CI chạy những gì

CI có **5 job**; mọi gate đều phải xanh **cả 5** trước khi merge vào `develop`:

| Job | Nội dung |
|---|---|
| `secret-scan` | gitleaks quét **toàn bộ lịch sử git** (`fetch-depth: 0`) |
| `validate-static` | tệp bắt buộc · JSON hợp lệ · `node --check` · chốt chặn QR giả · QR phải từ server · frontend không quay lại lưu lead ở `localStorage` · HTML không inline · không có secret dạng phổ biến |
| `backend` | ruff · `alembic upgrade head` + `alembic check` trên database sạch · unit test · integration test trên **PostgreSQL 16 service container** · full suite |
| `dependency-scan` | `pip-audit --strict` cho **cả** `requirements.txt` và `requirements-dev.txt` |
| `e2e` | **Chromium thật** + PostgreSQL 16 service container + chạy `pytest tests_e2e` |

**Ghi chú vận hành:** `pytest.ini` đặt `testpaths = tests`, nên lệnh `pytest` trần **không**
chạy `tests_e2e`. Job `e2e` gọi tường minh `pytest tests_e2e`. Cố ý như vậy: job `backend`
không có Chromium nên nếu gộp sẽ đỏ vì thiếu trình duyệt chứ không phải vì lỗi thật.

**Đã dính một lần:** trước đây CI chỉ **lint** `tests_e2e` mà **không chạy** nó — bộ E2E hỏng
vẫn qua CI. Một bộ test chỉ được lint thì **không bao giờ có thể FAIL**.
