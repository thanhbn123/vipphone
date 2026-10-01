# VIP PHONE

Landing nhận ốp điện thoại miễn phí cho cộng đồng **VIP ORDER × BNI** — kèm backend
thu lead, cấp gift code, tra cứu và phát quà có audit.

> **Trạng thái thật của repo nằm ở [`docs/MASTER_STATUS.md`](docs/MASTER_STATUS.md).**
> Đó là nguồn trạng thái chính. README chỉ tóm tắt; khi hai chỗ lệch nhau, tin `MASTER_STATUS.md`.

---

## 1. Hiện trạng

| Lớp | Trạng thái |
|---|---|
| Frontend | **CÓ** — HTML/CSS/JS thuần, không build step |
| Backend | **CÓ** — FastAPI (Python 3.12) |
| Database | **CÓ** — PostgreSQL 16 + Alembic migration (`0001_initial`) |
| Lưu trữ lead | **PostgreSQL** — server là nguồn chân lý duy nhất |
| QR | **PASS** — QR chuẩn ISO/IEC 18004 sinh ở server, đã kiểm bằng cách giải mã thật |
| Xác thực nhân viên | **CÓ** (khoá API). Chưa cấu hình thì **fail closed → 503** |
| Xác nhận phát quà | **CHƯA CÓ** → gate G03 |
| Admin leads | **CHƯA CÓ** → gate G05 |
| Test | **143 test PASS** trên PostgreSQL thật |
| GTM/GA4/Meta Pixel | **CHƯA NỐI** — mới có `window.dataLayer` |
| Staging | **NOT DEPLOYED** |
| Production | **NOT DEPLOYED** |

Kiến trúc đích và quyết định stack: [`docs/adr/0001-stack-selection.md`](docs/adr/0001-stack-selection.md).

---

## 2. Cấu trúc repo

```
# Frontend (không build step)
index.html success.html redeem.html admin-leads.html
assets/css/styles.css
assets/js/config.js        cấu hình (apiBase)
assets/js/tracking.js      dataLayer + thu thập src/ref/utm (whitelist)
assets/js/util.js          escape HTML, chuẩn hoá SĐT, gift code
assets/js/qr.js            render QR chuẩn lấy từ server
assets/js/app.js           landing: gọi POST /api/leads, đọc danh mục từ API
assets/js/success.js       trang thành công
assets/js/redeem.js        nhân viên: tra cứu + xác nhận phát quà
assets/js/qr-scan.js       quét QR bằng BarcodeDetector (chỉ khi trình duyệt hỗ trợ)
assets/js/admin-leads.js   quản trị: lead, lọc, phân trang, export CSV, danh mục iPhone

# Backend
app/main.py                app factory + static + router
app/config.py              cấu hình từ biến môi trường (pydantic-settings)
app/db.py                  engine, session, Base
app/models.py              SQLAlchemy models
app/schemas.py             Pydantic DTO (validate phía server)
app/phone.py               chuẩn hoá SĐT Việt Nam
app/giftcodes.py           sinh / chuẩn hoá gift code
app/security.py            security header, rate limit, xác thực nhân viên, Turnstile
app/audit.py               audit trail (metadata qua danh sách trắng)
app/services/              nghiệp vụ lead + gift + admin (truy vấn lead, CSV)
app/routers/               health, catalog, leads, gifts, admin
migrations/                Alembic
tests/                     pytest (unit + integration PostgreSQL)
tests_e2e/                 Playwright thật: máy chủ + PostgreSQL + Chromium (`make test-e2e`)

# Vận hành
.github/workflows/ci.yml   CI: gitleaks + kiểm tra tĩnh + backend trên PostgreSQL
.env.example               mẫu biến môi trường — KHÔNG chứa secret thật
Makefile alembic.ini pytest.ini ruff.toml requirements*.txt
docs/                      MASTER_STATUS, ADR, architecture, lead-schema
data/iphone-models.json    danh mục gốc (DB là nguồn chân lý; file này để tham chiếu)
```

---

## 3. Chạy local

### 3.1 Cần có

- Python **3.12**
- PostgreSQL **16**

### 3.2 Dựng môi trường

```bash
make venv             # tạo .venv bằng python3.12
make install-dev      # cài dependency + Playwright chromium

cp .env.example .env  # rồi sửa DATABASE_URL cho đúng máy bạn
```

### 3.3 Tạo database và chạy migration

```bash
createdb vipphone
# DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/vipphone

make migrate          # alembic upgrade head  → tạo bảng + seed 28 model iPhone
```

**Schema chỉ do migration tạo.** Ứng dụng không tự tạo bảng.

### 3.4 Chạy server

```bash
make run              # uvicorn trên http://localhost:8000
```

Mở <http://localhost:8000>. Tài liệu API tự sinh ở `/docs` (tắt khi `APP_ENV=production`).

### 3.5 Bật khu vực nhân viên

`STAFF_API_KEYS` để trống nghĩa là khu vực nhân viên **đóng** (API trả 503 — fail closed,
không mở toang). Muốn dùng:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"   # sinh khoá
# đặt vào STAFF_API_KEYS trong .env
```

Rồi mở <http://localhost:8000/redeem.html>, dán khoá vào ô "Khoá truy cập nhân viên".

---

## 4. Test

```bash
make test              # toàn bộ pytest — CẦN PostgreSQL thật
make test-unit         # chỉ unit test, không cần database
make lint              # ruff check + format --check
make migrate-check     # alembic upgrade head + alembic check
make secret-scan       # gitleaks trên toàn bộ lịch sử git
make test-e2e          # E2E TRÌNH DUYỆT THẬT (Chromium + máy chủ + PostgreSQL)
make check             # gộp: lint + test + secret-scan
```

`make test-e2e` dựng một máy chủ uvicorn thật trên database `_test`, mở Chromium
thật và đo hành vi DOM. Bộ này **không chạy trong CI**; chạy tay trước khi merge
khi có đụng tới HTML/JS. Nó là thứ duy nhất bắt được các lỗi như nút "đã ẩn" mà
vẫn hiện, hay landing không đọc danh mục từ API.

`TEST_DATABASE_URL` phải trỏ tới database có tên **kết thúc bằng `_test`**.
`tests/conftest.py` **từ chối chạy** nếu không đúng — để không xoá nhầm database thật.

Test dùng **PostgreSQL thật**, không dùng SQLite: chính sách chống trùng dựa trên
UNIQUE INDEX MỘT PHẦN, và redeem dựa trên khoá hàng — SQLite không có, test sẽ nói dối.

---

## 5. API

| Method | Path | Xác thực |
|---|---|---|
| GET | `/api/health` | công khai |
| GET | `/api/ready` | công khai |
| GET | `/api/catalog/iphone-models` | công khai |
| POST | `/api/leads` | công khai (rate limit; Turnstile nếu cấu hình) |
| GET | `/api/gifts/{gift_code}` | nhân viên |
| GET | `/api/gifts/{gift_code}/qr.png` | công khai |
| POST | `/api/gifts/{gift_code}/redeem` | nhân viên |
| GET | `/api/admin/leads` | **nhân viên** — lọc, phân trang, tổng số |
| GET | `/api/admin/leads.csv` | **nhân viên** — cùng bộ lọc, có trần dòng |
| GET | `/api/admin/leads/{lead_id}` | **nhân viên** — chi tiết |
| GET | `/api/admin/iphone-models` | **nhân viên** — cả model đã tắt |
| POST | `/api/admin/iphone-models` | **nhân viên** — thêm model |
| PATCH | `/api/admin/iphone-models/{model_code}` | **nhân viên** — sửa/tắt model |

Khu vực `/api/admin/*` **fail CLOSED**: chưa cấu hình `STAFF_API_KEYS` thì trả **503**,
không mở toang. Khoá gửi qua header `X-Staff-Key` hoặc `Authorization: Bearer …`.

```bash
curl -s localhost:8000/api/health
curl -s localhost:8000/api/ready
curl -s localhost:8000/api/catalog/iphone-models | head

curl -s -X POST localhost:8000/api/leads -H 'Content-Type: application/json' -d '{
  "full_name": "Nguyễn Văn A",
  "phone": "+84 912 345 678",
  "iphone_model": "iphone-16-pro-max",
  "case_color": "Đen",
  "source": "bni",
  "consent": true
}'
```

---

## 6. ⚠️ Giới hạn đã biết — đọc trước khi tin

Đây là bản đang phát triển, **chưa deploy ở đâu**. Cụ thể:

- **Chưa deploy ở đâu cả** (không staging, không production) ⇒ **không có cơ sở nào để
  nói "secure production"**. Xem `docs/MASTER_STATUS.md` §16.
- **Trang `admin-leads.html` được phục vụ công khai** (nó chỉ là cái vỏ, không chứa dữ liệu).
  Toàn bộ dữ liệu nằm sau `/api/admin/*` và đều bắt buộc xác thực.
- **Thay đổi danh mục iPhone chưa ghi audit** — cần thêm `event_type` mới + migration.
- **Export CSV không có BOM** ⇒ Excel có thể hiển thị sai dấu tiếng Việt khi mở trực tiếp.
- **Chưa nối GTM/GA4/Meta Pixel.** Mới có `window.dataLayer`.
- **Rate limit nằm trong bộ nhớ tiến trình** → chạy nhiều instance thì mỗi instance đếm riêng.
  Muốn chính xác khi scale ngang phải dùng Redis.
- **Turnstile mới có adapter**, chưa cấu hình secret thật ở đâu.
- **Bộ E2E đã có trong repo** (`tests_e2e/`, chạy bằng `make test-e2e`) nhưng **chưa nối vào CI** —
  CI không có Chromium. Một bộ test không chạy tự động là bộ test sẽ bị bỏ quên.
- **Chưa có `docs/deployment.md`** và **chưa có hạ tầng staging** — gate G11.

Danh sách đầy đủ: [`docs/MASTER_STATUS.md`](docs/MASTER_STATUS.md) §13.2.

---

## 7. Roadmap gate

| Gate | Nội dung | Trạng thái |
|---|---|---|
| G01 | Baseline hardening + sửa CI đỏ | **DONE** |
| G02 | Backend thật: API + PostgreSQL + migration + QR chuẩn + catalog | **DONE** |
| G03 | Redeem engine (atomic, chống double-spend) + audit | **DONE** |
| G04 | Staff redeem UI (quét QR) + ranh giới xác thực | **DONE** |
| G05 | Admin leads (tìm kiếm, lọc, phân trang, export CSV) | **DONE** |
| G06 | Danh mục iPhone: admin thêm/sửa model, không sửa HTML landing | **DONE** |
| G07 | Campaign / source / UTM tracking | một phần |
| G08 | Security pass đầy đủ | một phần |
| G09 | Test đầy đủ + E2E | một phần |
| G10 | CI đầy đủ | một phần |
| G11 | Staging readiness | một phần |
| G12 | Owner acceptance pack | chờ |

---

## 8. Luật vận hành repo

- **KHÔNG** commit thẳng lên `main`.
- **KHÔNG** force push `main` / `develop`.
- **KHÔNG** bỏ qua CI.
- **KHÔNG** commit secret hay credential. Dùng `.env` (đã ignore) và `.env.example`.
- **KHÔNG** deploy production khi chưa có lệnh release của Owner.
- Mọi thay đổi đi theo: issue → branch → code → test → PR → CI xanh → merge `develop`.
