# VIP PHONE

Landing nhận ốp điện thoại miễn phí cho cộng đồng **VIP ORDER × BNI** — kèm luồng
phát quà, tra cứu gift code và (đang xây) backend + admin.

> **Trạng thái thật của repo nằm ở [`docs/MASTER_STATUS.md`](docs/MASTER_STATUS.md).**
> Đây là nguồn trạng thái chính. README chỉ tóm tắt; khi hai chỗ lệch nhau, tin `MASTER_STATUS.md`.

---

## 1. Hiện trạng (đo ngày 2026-10-01)

| Lớp | Trạng thái |
|---|---|
| Frontend | **Có** — HTML/CSS/JS thuần, không build step |
| Backend | **CHƯA CÓ** |
| Database | **CHƯA CÓ** |
| Lưu trữ | `localStorage` của trình duyệt khách (chỉ để demo) |
| QR | **NOT_PRODUCTION** — chưa sinh mã QR chuẩn (xem §4) |
| Xác thực nhân viên | **CHƯA CÓ** — `STAFF AUTH = OPEN` |
| Test | **0 test** |
| Staging | **NOT DEPLOYED** |
| Production | **NOT DEPLOYED** |

Kiến trúc đích và quyết định stack: [`docs/adr/0001-stack-selection.md`](docs/adr/0001-stack-selection.md)
(**Python + FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL 16**).

---

## 2. Có gì trong repo

```
index.html                      landing thu lead
success.html                    hiển thị gift code sau khi đăng ký
redeem.html                     giao diện nhân viên xác nhận phát quà
assets/css/styles.css           giao diện
assets/js/tracking.js           dataLayer + thu thập src/ref/utm (whitelist)
assets/js/util.js               escape HTML, chuẩn hoá SĐT, gift code
assets/js/qr.js                 render QR — hiện là NOT_IMPLEMENTED (xem §4)
assets/js/app.js                landing: validation, chống trùng, sinh gift code
assets/js/success.js            trang thành công
assets/js/redeem.js             nhân viên: tra cứu + xác nhận phát quà
data/iphone-models.json         danh mục iPhone theo năm
docs/MASTER_STATUS.md           NGUỒN TRẠNG THÁI CHÍNH
docs/adr/0001-stack-selection.md quyết định stack backend
docs/architecture.md            kiến trúc
docs/lead-schema.md             schema lead
.github/workflows/ci.yml        CI: gitleaks + kiểm tra tĩnh
```

---

## 3. Chạy local

Không mở `index.html` trực tiếp bằng `file://` — trình duyệt sẽ chặn `fetch()`
khiến danh mục iPhone không tải được.

```bash
python3 -m http.server 8080
# mở http://localhost:8080
```

---

## 4. ⚠️ QR hiện tại KHÔNG phải mã QR thật

Bản starter cũ có `assets/js/qr-lite.js` vẽ một hình **trông giống** mã QR nhưng
bit sinh từ hash + PRNG, **không theo chuẩn ISO/IEC 18004**. Không đầu đọc QR nào
quét được hình đó. Một hình giả trông như thật là cái bẫy ngay tại quầy phát quà.

File đó **đã bị gỡ**. `assets/js/qr.js` hiện chủ động **không vẽ hình giống QR**,
mà hiển thị:

- dòng chữ *"Mã QR chưa khả dụng"*,
- URL nhận quà dạng văn bản,
- nút sao chép liên kết.

QR chuẩn (thư viện `qrcode`, sinh ở server, chỉ chứa URL công khai + gift code —
**không chứa PII**) được thêm ở gate **G02**. CI có chốt chặn để QR giả không
quay lại.

---

## 5. ⚠️ Giới hạn của bản demo hiện tại

Đây là bản demo client-only. Cụ thể:

- Lead chỉ nằm trên **đúng trình duyệt** đã đăng ký. Nhân viên ở máy khác **không thấy**.
- Xoá dữ liệu trình duyệt = **mất lead**. Không có nguồn chân lý.
- Chống trùng chỉ chạy ở client → đổi trình duyệt là vô hiệu.
- Validation chỉ ở client → sửa được bằng DevTools.
- `redeem.html` mở công khai, **không có xác thực nhân viên**.
- Không rate limit, không audit trail, không chống double-spend.
- Không có security header (chưa có server để đặt).

Danh sách lỗ hổng đầy đủ: [`docs/MASTER_STATUS.md`](docs/MASTER_STATUS.md) §1.11.

---

## 6. Roadmap gate

| Gate | Nội dung |
|---|---|
| G01 | Baseline hardening + sửa CI đỏ |
| G02 | Backend thật: API + PostgreSQL + migration |
| G03 | Redeem engine (atomic, chống double-spend) + audit log |
| G04 | Staff redeem UI + xác thực nhân viên |
| G05 | Admin leads (tìm kiếm, lọc, phân trang, export CSV) |
| G06 | Danh mục iPhone trong database |
| G07 | Campaign / source / UTM tracking |
| G08 | Security pass |
| G09 | Test (14 kịch bản bắt buộc + E2E) |
| G10 | CI đầy đủ (lint, unit, integration PostgreSQL, migration check, secret scan) |
| G11 | Staging readiness (`.env.example`, `/api/ready`, `docs/deployment.md`) |
| G12 | Owner acceptance pack |

Tiến độ thật: xem bảng "TRẠNG THÁI GATE" trong [`docs/MASTER_STATUS.md`](docs/MASTER_STATUS.md) §3.

---

## 7. Luật vận hành repo

- **KHÔNG** commit thẳng lên `main`.
- **KHÔNG** force push `main` / `develop`.
- **KHÔNG** bỏ qua CI.
- **KHÔNG** commit secret hay credential. Dùng `.env` (đã ignore) và `.env.example`.
- **KHÔNG** deploy production khi chưa có lệnh release của Owner.
- Mọi thay đổi đi theo: issue → branch → code → test → PR → CI xanh → merge `develop`.

---

## 8. Kiểm tra chất lượng tại máy

```bash
# Secret scan (cùng phiên bản CI dùng)
gitleaks git --no-banner --redact

# Cú pháp JavaScript
for f in assets/js/*.js; do node --check "$f"; done

# JSON hợp lệ
python3 -m json.tool data/iphone-models.json > /dev/null
```
