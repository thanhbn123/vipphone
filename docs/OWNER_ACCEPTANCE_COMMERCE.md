# NGHIỆM THU OWNER — PHẦN THƯƠNG MẠI (G15 → attribution)

- Ngày đo: **2026-10-07** (UTC)
- Người đo: DEEPSEEK HARNESS — COMMERCE COMPLETION
- `develop` trước PR #83: `34afdf3c99a9ca9973133d848d28ead212c414b9` (đỉnh mới đọc bằng `git rev-parse origin/develop` — ghi một giá trị sẽ sai ngay sau khi ghi) · `main`: `7d6162cf31eb96ea27879be3a4671812a9cd7e01` — **KHÔNG ĐỔI**
- **STAGING (`https://qua.viporder.vn`): CHƯA triển khai các gate dưới đây** — xem §C và D-006.
- **Đo lại 2026-10-08** (phiên "FINAL STAGING DEPLOYMENT"): `develop` = `31a95498883d9a4287549115065d2ea96197a244`
  (CI xanh), 0 PR/issue mở, staging **vẫn không tới được** từ phiên harness ⇒ không có số đo staging mới.
  Lượt này chỉ chuẩn bị cho lần chạy staging thật — §E.
- **Đo lại 2026-10-10 (Owner chạy từ MacBook, staging THẬT):** `develop` = `85a5f066b4d9ae005955a334a1c111c1404ecc7d`,
  **staging = develop** (`current → 20261010-013751-85a5f06`, head `0014`, 24 bảng). Toàn runbook 27/27 bước qua — §H.
  Bốn hạng mục BLOCKED/NOT RUN ở bảng A nay **PASS (staging)**.
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
| Trang admin bán hàng | #82 | **PASS (repo)** | E2E: nhân viên thao tác đơn, xác nhận tiền, kho, giá, ảnh, báo cáo |
| Hành trình 20 bước | #82 | **PASS (tại máy + CI 3 engine)** | `tests_e2e/test_integrated_journey.py` |
| Hồi quy quà tặng | mọi PR | **PASS** | toàn bộ bộ funnel/redeem cũ xanh ở mọi PR; bước 20 hành trình |
| Bảo mật | #83 | **PASS (repo)** — có 1 lỗi thật đã sửa | §B |
| Migration | — | **PASS (tại máy + CI + staging)** | head `0014_order_attribution`; `alembic check` sạch; 24 bảng; staging `0007 → 0014` 2026-10-10 (§H) |
| Sao lưu / phục hồi | #82 | **PASS tại máy + staging** | `scripts/restore_drill.py --docker-pg` trên máy chủ: 24/24 bảng khớp md5 (§H); đối chứng âm phát hiện bản hỏng |
| Rollback mã | — | **PASS tại máy + staging** | staging: `rollback.sh` B'→B health 200, verify 11/11, deploy lại 11/11 (§H); tại máy: mã `develop@G17` trên schema `0014`: 12/12 khói |
| Script deploy trên staging thật | #94, #96 | **PASS (staging thật, 2026-10-10)** | `staging.sh` + `verify.sh` 11/11 phiếu PASS trên `160.22.170.20`; sau 2 lỗi chỉ hiện trên máy thật (bash 3.2 #92, scp SFTP #95) — §H |
| Nghiệm thu staging thương mại | — | **PASS (staging thật)** | `staging_commerce_smoke.py` **24/24** trên `https://qua.viporder.vn`; hồi quy quà 28 PASS; trình duyệt 96/96; tải 0 lỗi — §H |
| Dọn dữ liệu test | #82 | **PASS tại máy + staging** | staging: đếm → xoá 3 đơn/3 thanh toán/2 lead/… → còn 0 marker; `leads` trước = sau = 0 dòng; từ chối production |
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


## E. Chuẩn bị cho lần chạy staging thật (2026-10-08, PR #85)

Ba lỗi THẬT tìm được khi rà đường deploy (không cần staging để tìm, nên đã sửa luôn):

| Lỗi | Hậu quả nếu deploy | Sửa |
|---|---|---|
| Không có chốt "sai host": đặt nhầm `STAGING_HOST=160.22.171.228` thì `staging.sh` chạy migration + thay container trên **production** | đụng production | `require_host` từ chối host trong `KNOWN_PRODUCTION_HOSTS` / trùng `PRODUCTION_HOST` (và ngược lại); 4 ca thử, đối chứng âm đỏ |
| `MEDIA_ROOT=` (rỗng) được đọc thành `Path('.')` | ảnh ghi vào thư mục mã trong container, **mất ở lần deploy sau** | rỗng ⇒ mặc định `/app/var/media` (volume); có test + đối chứng âm |
| `.env.staging.example` không có biến nào của G16/G17/ảnh; preflight không kiểm cấu hình thương mại | thiếu cấu hình mà không ai biết; khoá webhook giả lập có thể lọt sang production | thêm mục THƯƠNG MẠI; preflight: khoá giả lập ở production ⇒ FAIL, khoá yếu ⇒ FAIL, phí ship/hướng dẫn CK ⇒ WARN (D-008/D-009) |

Công cụ mới cho lần chạy thật — **runbook một-lượt**: `docs/STAGING_RUNBOOK_COMMERCE.md`.

- `scripts/staging_browser_check.py` — 3 engine × 4 độ rộng × các trang công khai, chỉ đọc: tràn ngang, lỗi console,
  tài nguyên hỏng, mixed content. Tại máy (Chromium): 14/14; đối chứng âm (xoá tệp ảnh) ⇒ 2 ô FAIL đúng.
- `scripts/restore_drill.py --docker-pg` — diễn tập phục hồi chạy TRÊN máy chủ chỉ với `python3` hệ thống
  (image ứng dụng không có `pg_dump`). Trên container `postgres:16` giả lập staging tại máy: 24/24 bảng khớp md5;
  đối chứng âm ⇒ FAIL đúng; DB tạm luôn bị xoá.

## F. Lỗi chặn deploy thứ tư (2026-10-08, issue #86)

Rà lại script trước lượt chạy thật, dựng lại đúng hình dạng staging vừa đo (container G14 giữ `0.0.0.0:18080`)
bằng Docker thật: `docker_promote` dừng bản cũ bằng **glob của shell** (`"$container-prev-"*`) — glob khớp tên
file chứ không phải tên container ⇒ bản cũ chạy tiếp, giữ cổng ⇒ `docker run` bản mới hỏng
`port is already allocated` ở **mọi** lượt deploy, sau khi đã migration. Sửa: lọc bằng `docker ps --filter`;
bản mới không chạy được thì tự dựng lại bản trước và thoát ≠ 0; `rollback.sh` gắn volume ảnh.
`deploy/tests/thu-promote-docker.sh`: 12/12; mã cũ ⇒ 9 FAIL (đối chứng âm).

## G. Diễn tập trên BẢN SAO staging — 8 lỗi chặn nữa (2026-10-08, issue #88)

Số đo thật từ máy chủ (qua SSH của Owner): G14 `c9ab9d1` trên `0.0.0.0:18080`, DB `0007`/11 bảng, Caddy trên host,
`18081` thuộc `viporder-nginx-1`, app trả `Invalid host header` khi gọi `127.0.0.1`. Dựng bản sao đúng như thế rồi
chạy nguyên runbook. Mỗi lỗi dưới đây đều làm lượt staging thật hỏng:

| # | Lỗi | Hậu quả trên máy thật | Sửa + bằng chứng |
|---|---|---|---|
| 1 | cổng tạm = 18080+1 = 18081 (của dự án khác) | chết ở bước 7, **sau migration** | `STAGING_TEMP_PORT=18180` + `require_ports` trước backup; đối chứng âm DỪNG ở bước 3 |
| 2 | health/verify gọi `127.0.0.1` không có Host | bản mới luôn "không khoẻ"; verify luôn FAIL | `host_header` từ `STAGING_URL`; chốt tĩnh |
| 3 | verify kiểm `/assets/css/main.css` | luôn 404 FAIL | `styles.css`; `tests/test_deploy_verify_paths.py` |
| 4 | verify kiểm `/api/config` | luôn 404 FAIL | `/api/public-config`; cùng test, đối chứng âm đỏ |
| 5 | băm cây máy chủ gồm `release.json` | verify luôn "mã KHÁC Git" | loại `release.json` khỏi phép băm |
| 6 | verify gọi ngay khi container chính chưa nghe | verify 000; **production.sh sẽ tự rollback** | `docker_promote` chờ health 200, không khoẻ ⇒ dựng lại bản trước; ca thử 4 |
| 7 | `mv -f` lên symlink `current`/`previous` | rollback: container về bản cũ, `current` vẫn trỏ bản mới; từ lượt 3 `previous` đứng yên ⇒ rollback sai bản | `mv -Tf`; ca thử 2b, đối chứng âm 5 FAIL |
| 8 | `staging_acceptance.sh` gán cứng `PY=$HOME/Projects/vipphone/...` | trên Mac khác: catalog "0 model", không redeem được | venv của repo / `python3`; nhận `STAFF_KEY`; đối chứng âm thoát 2 |

Kèm: test `test_selling_below_cost_price_is_allowed` đỏ ngẫu nhiên (khớp chuỗi "999" trong UUID) ⇒ so theo giá trị;
`${VAR^^}` (bash 4) thay bằng biến thường cho bash 3.2 của macOS.

## H. Staging THẬT — toàn runbook qua (2026-10-10, Owner chạy từ MacBook)

Lệnh: `bash scripts/owner_staging_run.sh` trên MacBook của Owner (`/bin/bash` 3.2.57, OpenSSH 10.3). Chi tiết từng bước,
bốn lượt chạy và hai lỗi mới chỉ hiện trên máy thật: `MASTER_STATUS.md` §40. Log: `staging-run-20261010-013035/` (0 tệp chứa secret).

| Gate | Trên staging thật | Số đo |
|---|---|---|
| Cửa khoá | PASS | IP `160.22.170.20`, DB `vipphone_staging`, Caddy → `127.0.0.1:18080` (admin API); `thu-deploy.sh` 86/86; 3 đối chứng âm DỪNG đúng |
| Deploy + migration | PASS | `0007 → 0014`, 24 bảng, `alembic check` sạch; bản G14 `c9ab9d1` đã dừng, `verify.sh` 11/11 + phiếu PASS |
| Preflight | PASS (3 WARN chủ ý) | Turnstile tắt (D-002), `SHIPPING_FEE_FLAT=0` (D-008), 1 khoá nhân viên |
| Thương mại A→J | PASS | `staging_commerce_smoke.py` 24/24 (run `26EDEF`) |
| Hồi quy quà | PASS | 28 PASS · 0 FAIL · 1 BLOCKED (ca cần DB, đã phủ bởi verify) |
| Trình duyệt | PASS | 96/96: 3 engine × 4 độ rộng × 8 trang, 0 tràn ngang, 0 lỗi console, 0 tài nguyên hỏng |
| Tải nhẹ | PASS | 1 400 req / 32,9 s, 0 lỗi, 0 × 429, p95 344 ms, `restart=0` |
| Sao lưu + phục hồi | PASS | dump đọc được; `restore_drill.py --docker-pg`: 24/24 bảng khớp md5; DB tạm đã xoá |
| Rollback | PASS | B'→B health 200 + verify 11/11; deploy lại verify 11/11 |
| Log + dọn | PASS | 0 dòng lỗi, 0 PII/secret; marker còn 0; `leads` trước lượt = 0 (dump 01:31:22), sau = 0 |

**Không đổi:** `main` `7d6162c`; PRODUCTION NOT DEPLOYED; `enforce_admins` không đổi. **Owner còn phải quyết:** D-002, D-007, D-008, D-009, D-010 (xem `OWNER_DECISIONS_REQUIRED.md`).

