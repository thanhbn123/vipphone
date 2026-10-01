# ADR-0001 — Chọn stack backend cho VIP PHONE

- **Ngày:** 2026-10-01
- **Trạng thái:** Accepted
- **Người quyết định:** DEEPSEEK HARNESS — VIP PHONE PROJECT CONTROLLER
- **Bối cảnh gate:** G01 (chuẩn bị cho G02)

---

## 1. Vấn đề

Repo `vipphone` ở baseline `7d6162c` là **frontend tĩnh thuần** (14 file, không `package.json`, không backend, không database). Toàn bộ nghiệp vụ lead/gift/redeem chạy trong `localStorage` của trình duyệt.

Cần chọn một stack backend để đạt kiến trúc đích:

```
Frontend → API → Database → Gift Engine → Redeem → Admin → Analytics/CRM
```

Ràng buộc từ yêu cầu dự án:

- Có **migration** (không auto-create schema production bằng side effect khó kiểm soát).
- Có **transaction/atomic update** cho redeem, chống double-spend khi concurrent.
- Có **validate server-side** và không tin dữ liệu client.
- Có **test** đầy đủ (14 kịch bản bắt buộc + integration PostgreSQL + migration check).
- **Đơn giản, ổn định, dễ deploy, dễ rollback, dễ maintain.** Không over-engineer.
- Không dùng secret thật, không phụ thuộc hạ tầng ngoài chưa có.

---

## 2. Phương án đã cân nhắc

### Phương án A — Python + FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL ✅ CHỌN

**Ưu điểm đo được với repo này:**

1. **CI hiện tại đã dùng Python.** `.github/workflows/ci.yml` baseline có bước `python -m json.tool`. Thêm backend Python **không thêm toolchain mới nào** vào CI; thêm backend Node thì phải dựng `package.json`, lockfile, npm cache từ số 0.
2. **Pydantic** cho validation khai báo được, sinh **OpenAPI/Swagger miễn phí** tại `/docs` → Owner và verifier tự kiểm API mà không cần đọc code.
3. **Alembic** là công cụ migration trưởng thành nhất trong hai phương án: có `upgrade`/`downgrade`, `history`, `current`, và **autogenerate diff** — đúng yêu cầu "migration check" ở G10 (so schema thật với migration head).
4. **SQLAlchemy 2.0** cho quyền kiểm soát transaction tường minh: `SELECT ... FOR UPDATE` trên PostgreSQL là cách trực tiếp và dễ chứng minh nhất cho yêu cầu **concurrent redeem không double-spend** (G03). Khoá hàng ở tầng DB, có test chứng minh.
5. **pytest** + `httpx`/`TestClient` cho integration test; **Playwright (Python)** cho E2E trình duyệt thật — một toolchain chạy cả ba tầng test.
6. **Một tiến trình phục vụ cả API lẫn frontend tĩnh** (`StaticFiles`) → deploy 1 service + 1 database, rollback = trỏ lại image/tag cũ. Khớp yêu cầu "dễ deploy, dễ rollback".
7. **Không cần build step cho frontend.** Giữ nguyên HTML/CSS/JS thuần hiện có — không phá baseline, không thêm rủi ro bundler.

**Nhược điểm và cách chấp nhận:**

- Hai ngôn ngữ trong repo (Python backend + JS frontend). Chấp nhận: frontend **không có build step**, nên không phát sinh chuỗi công cụ JS phải bảo trì. Không dùng chung type được — bù bằng OpenAPI schema và test E2E.
- Python 3.9 hệ thống quá cũ → chốt **Python 3.12** cho app và CI.

### Phương án B — Node.js + Fastify/Express + PostgreSQL (qua Prisma/Drizzle) ❌ LOẠI

Khả thi về kỹ thuật, nhưng:

- Phải dựng toolchain JS từ số 0 trong khi frontend cố tình **không có build step** → lợi thế "một ngôn ngữ" bị vô hiệu phần lớn.
- Không có ưu thế nào vượt trội cho yêu cầu **concurrent redeem**: khoá hàng vẫn phải viết SQL thủ công hoặc dựa vào transaction của ORM, không rõ ràng hơn `FOR UPDATE`.
- Thêm `node_modules` (hàng trăm MB) vào một repo hiện chỉ 25 KB — tăng bề mặt supply-chain mà không đổi lại lợi ích tương xứng.

**Kết luận:** loại vì không giải quyết yêu cầu nào tốt hơn A, mà lại thêm một toolchain.

### Phương án C — BaaS / serverless có quản lý (Supabase, Firebase, Cloudflare D1…) ❌ LOẠI

- Cần **credential và hạ tầng bên ngoài thật** → rơi đúng vào điều kiện STOP số 1 và số 3.
- Khoá dữ liệu khách (PII) vào nhà cung cấp, khó rollback, khó kiểm toán.
- Không đáp ứng yêu cầu "migration" một cách tường minh và kiểm chứng được trong CI.

### Phương án D — Giữ nguyên client-only, chỉ hardening ❌ LOẠI

Không thể đạt bất kỳ yêu cầu nào của G02–G05: không có nguồn chân lý, không chống double-spend, không audit, không admin. Đây chính là hiện trạng đang có.

---

## 3. Quyết định

**Chọn Phương án A.**

| Thành phần | Chọn | Phiên bản |
|---|---|---|
| Ngôn ngữ runtime | Python | **3.12** |
| Web framework | FastAPI | `~=0.115` |
| ASGI server | Uvicorn | `~=0.32` |
| Validation / settings | Pydantic v2 + pydantic-settings | `~=2.9` / `~=2.6` |
| ORM | SQLAlchemy | `~=2.0` |
| Migration | Alembic | `~=1.14` |
| Database | PostgreSQL | **16** |
| Driver | psycopg (v3) | `~=3.2` |
| Test | pytest + httpx | `~=8.3` / `~=0.28` |
| E2E | Playwright (Python) | `~=1.49` |
| Lint | ruff | `~=0.8` |
| QR | `qrcode[pil]` (chuẩn ISO/IEC 18004) | `~=8.0` |

Phiên bản cụ thể sẽ bị ghim trong `requirements.txt` / `requirements-dev.txt` ở G02; bảng trên là ràng buộc tương thích.

### 3.1 Bố cục repo sau G02

```
vipphone/
├── app/                      # backend FastAPI
│   ├── main.py               # app factory + router + StaticFiles
│   ├── config.py             # Settings (pydantic-settings)
│   ├── db.py                 # engine, session, Base
│   ├── models.py             # SQLAlchemy models
│   ├── schemas.py            # Pydantic DTO
│   ├── security.py           # staff auth, rate limit, security headers
│   ├── services/             # gift engine, audit, redeem, catalog
│   └── routers/              # leads, gifts, catalog, admin, health
├── migrations/               # Alembic
├── tests/                    # pytest (unit + integration PostgreSQL)
├── tests_e2e/                # Playwright
├── web/                      # frontend (chuyển từ gốc repo vào đây ở G02)
├── docs/                     # MASTER_STATUS, ADR, deployment, acceptance
├── .env.example
├── Makefile
└── requirements*.txt
```

### 3.2 Quyết định kèm theo

- **PostgreSQL là database duy nhất được test.** CI dùng service container PostgreSQL 16. Không dùng SQLite cho integration test vì khác biệt về khoá hàng/`FOR UPDATE`/kiểu dữ liệu sẽ làm test nói dối về hành vi thật.
- **Không auto-create schema.** Schema chỉ do Alembic tạo. App **không** gọi `create_all()` khi khởi động ở mọi môi trường trừ test dùng migration.
- **Frontend giữ nguyên vanilla.** Không thêm framework, không thêm build step.
- **Một tiến trình** phục vụ API + static, để deploy/rollback đơn giản.

---

## 4. Hệ quả

### Tích cực
- Migration có kiểm chứng (`alembic upgrade head` chạy trong CI trên PostgreSQL sạch).
- Redeem atomic chứng minh được bằng test concurrent thật.
- OpenAPI tự sinh → nghiệm thu không cần đọc code.
- Rollback đơn giản: một service, một image tag, migration có `downgrade`.

### Tiêu cực / rủi ro đã biết
- Thêm rủi ro supply-chain Python → giảm thiểu bằng ghim phiên bản + CI dependency scan (G10).
- Rate limiter trong tiến trình **không** chia sẻ giữa nhiều worker → ghi rõ giới hạn, cần Redis khi scale ngang (ghi ở G08/G11, không giả vờ là đủ cho production nhiều instance).
- Hai ngôn ngữ → phải giữ OpenAPI và frontend khớp nhau; bù bằng E2E Playwright.

### Việc phải làm ngay ở G02
1. Dựng `app/`, `migrations/`, `requirements*.txt`, `Makefile`.
2. Viết migration đầu tiên cho `leads`, `audit_events`, `iphone_models`.
3. Bật PostgreSQL 16 trong CI bằng service container.

---

## 5. Tham chiếu

- Yêu cầu dự án: TARGET ARCHITECTURE, G02, G03, G09, G10, G11.
- Hiện trạng đo được: [`docs/MASTER_STATUS.md`](../MASTER_STATUS.md) §1.
