# NGHIỆM THU OWNER — PHẦN THƯƠNG MẠI (G15 → attribution)

- Ngày đo: **2026-10-07** (UTC)
- Người đo: DEEPSEEK HARNESS — COMMERCE COMPLETION
- `develop` cuối: `{{FINAL_DEVELOP}}` · `main`: `7d6162cf31eb96ea27879be3a4671812a9cd7e01` — **KHÔNG ĐỔI**
- **STAGING (`https://qua.viporder.vn`): CHƯA triển khai các gate dưới đây** — xem §C và D-006.
- **PRODUCTION: NOT DEPLOYED.**

> Luật đọc bảng: `PASS` chỉ khi có lệnh đã chạy và số đo đứng sau. Chưa đo được ⇒ `BLOCKED`/`NOT RUN`
> kèm lý do. "Tại máy" = container của harness (PostgreSQL 16 thật, Chromium thật); "CI" = GitHub Actions
> (Chromium + Firefox + WebKit thật). **Không mục nào dưới đây là số đo trên staging.**

## A. Từng hạng mục

| Hạng mục | PR | Kết quả | Bằng chứng chính |
|---|---|---|---|
| Branch protection | (đo + #65) | **PASS** | 4 check bắt buộc = 4 job tự động; PR có check bắt buộc đỏ ⇒ `blocked` |
| G15 gợi ý phụ kiện | #66 | **PASS (repo)** | thứ tự xác định, đúng máy, SKU/sản phẩm/nhóm tắt bị loại, không ốp sau quà; 4 đối chứng âm |
| G16 giỏ + đơn | #68 | **PASS (repo)** | giả giá, idempotency, 8 luồng đồng thời ⇒ 1 đơn, IDOR, SKU tắt, địa chỉ sai, chuyển trạng thái; 8 đối chứng âm |
| G17 thanh toán | #70 | **PASS (repo)** | COD không tự PAID, chuyển khoản chờ nhân viên, webhook: chữ ký/chống trùng/số tiền/tiền tệ/khớp/chuyển trạng thái; 7 đối chứng âm |
| Kho tối giản | #72 | **PASS (repo)** | 10 checkout đồng thời / tồn 3 ⇒ đúng 3 đơn; sổ cái khớp số dư; 4 đối chứng âm |
| Lịch sử giá | #74 | **PASS (repo)** | trigger DB nguyên tử; đổi giá 1 dòng, thất bại 0 dòng; ảnh chụp đơn không đổi |
| Ảnh sản phẩm | #80 | **PASS (repo)** | magic bytes + Pillow + xoá EXIF; không có đường URL ngoài; volume media cho staging |
| Attribution | #81 | **PASS (repo)** | first-touch không ghi đè; báo cáo nguồn tạo khách / chiến dịch ra đơn / referrer ra doanh thu |
| Trang admin bán hàng | {{PR_ADMIN}} | **PASS (repo)** | E2E: nhân viên thao tác đơn, xác nhận tiền, kho, giá, ảnh, báo cáo |
| Hành trình 20 bước | {{PR_OPS}} | **PASS (tại máy + CI 3 engine)** | `tests_e2e/test_integrated_journey.py` |
| Hồi quy quà tặng | mọi PR | **PASS** | toàn bộ bộ funnel/redeem cũ xanh ở mọi PR; bước 20 hành trình |
| Bảo mật | {{PR_SEC}} | **PASS (repo)** — có 1 lỗi thật đã sửa | §B |
| Migration | — | **PASS (tại máy + CI)** | head `0014_order_attribution`; `alembic check` sạch; 24 bảng |
| Sao lưu / phục hồi | {{PR_OPS}} | **PASS tại máy · NOT RUN staging** | `scripts/restore_drill.py`: 24/24 bảng khớp md5; đối chứng âm phát hiện bản hỏng |
| Rollback mã | — | **PASS tại máy · NOT RUN staging** | mã `develop@G17` chạy trên schema `0014`: 12/12 khói, 0 traceback |
| Script deploy trên staging thật | — | **BLOCKED** (D-006) | bộ thử deploy 66/66 tại máy; không có đường mạng/khoá SSH tới staging |
| Nghiệm thu staging thương mại | — | **BLOCKED** (D-006) | `scripts/staging_commerce_smoke.py` 24/24 trên máy chủ `APP_ENV=staging` tại máy |
| Dọn dữ liệu test | {{PR_OPS}} | **PASS tại máy** | đếm → xoá → còn 0 marker; dữ liệu thật giữ nguyên; từ chối production |
| Turnstile thật | — | **BLOCKED_EXTERNAL_CREDENTIAL** | D-002 |
| Cổng thanh toán thật | — | **NOT INTEGRATED** | ranh giới cho phép |

## B. Bảo mật — đo bằng runtime

| Mục | Kết quả |
|---|---|
| Quét phụ thuộc (`pip-audit` requirements + dev) | 0 lỗ hổng đã biết (tại máy + job CI bắt buộc) |
| Quét secret (`gitleaks` toàn lịch sử) | sạch (tại máy + job CI bắt buộc) |
| IDOR giỏ / đơn / ảnh | sai token ⇒ 404 giống "không tồn tại"; ảnh sản phẩm khác ⇒ 404 |
| Giả giá | body có trường giá ⇒ 422; `expected_total` lệch ⇒ 409, không tạo đơn |
| Quyền admin | `test_no_api_route_is_unexpectedly_public` dò **mọi** route `/api` (gồm route mới) |
| Webhook | chữ ký HMAC + chặn timestamp cũ; sai ⇒ 401, không ghi DB |
| PII trong analytics | E2E kiểm theo khoá **và** theo giá trị thật trên toàn hành trình |
| PII trong log | **LỖI THẬT ĐÃ SỬA**: lỗi SQL in tham số (tên, SĐT); PostgreSQL `DETAIL` in dữ liệu dòng; access log ghi `?q=<SĐT>` ⇒ che 3 lớp, test bằng uvicorn thật |
| PII trong vết | `order_status_events`/`payment_events`/`inventory_movements`/`price_history`: không cột PII; `payment_events` không lưu payload thô/chữ ký |
| Rate limit | bộ đếm riêng cho tạo giỏ/checkout ⇒ 429 + `Retry-After` |
| CORS | origin lạ không được cấp ACAO trên checkout/giỏ/webhook |
| CSRF / phiên | không cookie nào được đặt ⇒ không bề mặt CSRF; quyền nằm ở header token |
| Header | CSP `script-src 'self'` không `unsafe-*` trên mọi trang mới; `X-Frame-Options: DENY` |

## C. Bảng này KHÔNG nói gì

- **Không** có số đo nào trên `https://qua.viporder.vn` cho các gate này: phiên của harness bị proxy chặn
  (`CONNECT … 403`) và không có khoá SSH (D-006). `develop ≠ staging`.
- Script deploy mới (`deploy/*.sh`) **chưa** chạy thật lần nào trên staging.
- Phí ship mặc định `0.00` (D-008); hướng dẫn chuyển khoản trống (D-009); ảnh production chưa có kho bền (D-010).

## D. Owner làm gì tiếp

1. Chọn một cách ở **D-006** để chạy `deploy/staging.sh` + `scripts/staging_commerce_smoke.py` +
   `scripts/cleanup_test_data.py` + `scripts/restore_drill.py` trên staging (khối lệnh nằm ở D-006).
2. Quyết D-007 (enforce_admins), D-008 (phí ship), cung cấp D-009 (nội dung chuyển khoản), chọn D-010 (kho ảnh).
3. Không merge `develop → main` cho tới khi có lệnh phát hành của Owner.
