# Triển khai trực tiếp (direct deploy) — VIP PHONE

> **Chốt ngày 07/10/2026, anh Thành duyệt.** GitHub Actions **không còn** là cửa
> quyết định triển khai. GitHub giữ ba việc: lưu mã, lưu lịch sử Git, đánh tag.
>
> **Trạng thái thật lúc viết (07/10/2026 19:0x +0700):**
>
> | | |
> |---|---|
> | Bộ script triển khai | **CÓ** — `deploy/`, 57/57 ca thử tại máy đạt |
> | Bộ test tại máy | **ĐẠT** — 418 passed · 1 skipped, PostgreSQL 16.15 thật |
> | Staging đã triển khai bằng bộ này | **CHƯA** — xem §9, thiếu khoá SSH trên máy này |
> | Production | **CHƯA** triển khai, và chưa có host |
>
> Tài liệu này mô tả **cách triển khai** và **cái gì đã được đo**. Chỗ nào chưa
> đo thì nói là chưa đo.

---

## 1. Luồng chuẩn

```
LOCAL CODE → LOCAL TEST → VPS STAGING → STAGING VERIFY
           → OWNER ACCEPTANCE → VPS PRODUCTION → PRODUCTION VERIFY
           → GIT PUSH / TAG
```

Năm lệnh Owner cần dùng, không có lệnh thứ sáu:

```bash
./deploy/staging.sh                 # test tại máy → đóng gói → lên staging
./deploy/verify.sh staging          # nghiệm thu; CHỈ lệnh này sinh phiếu cho production
./deploy/production.sh              # chỉ nhận bản đã có phiếu, đúng SHA
./deploy/verify.sh production       # nghiệm thu production
./deploy/rollback.sh production     # quay về bản trước
```

Thêm hai lệnh phụ:

```bash
./deploy/backup.sh production            # sao lưu riêng, không gắn lượt deploy nào
DEPLOY_DRY_RUN=1 ./deploy/staging.sh     # in kế hoạch, KHÔNG chạm máy chủ
```

### Bốn cửa khoá, cả bốn fail closed

| Cửa | Chặn gì | Hỏng thì sao |
|---|---|---|
| Cây làm việc sạch | mã chưa commit = mã không có SHA | dừng, **không** tự stash, **không** xoá gì của bạn |
| Test tại máy | lượt chưa test không đi lên staging | dừng; thiếu venv cũng dừng, **không** bỏ qua test |
| Phiếu staging PASS | bản chưa nghiệm thu không vào production | dừng; phiếu của SHA khác cũng bị từ chối |
| Mã băm gói | production phải là **đúng gói** đã test | dừng khi băm lệch |

---

## 2. Chạy test tại máy

Bộ test **cần một PostgreSQL sống** — `tests/conftest.py` nối database ở mức
session, nên cả test không gắn nhãn `integration` cũng cần. Tên database **phải**
kết thúc bằng `_test` (chốt an toàn trong `conftest.py`).

Cụm tạm, không đụng dịch vụ hệ thống (đã chạy thật trên Mac mini 07/10/2026):

```bash
PGB=/opt/homebrew/opt/postgresql@16/bin
D=/tmp/vipphone-pg; PORT=55517
env LANG=C LC_ALL=C "$PGB/initdb" -D "$D" -U vipphone --auth=trust -E UTF8 --locale=C
env LANG=C LC_ALL=C "$PGB/pg_ctl" -D "$D" -l "$D/pg.log" \
  -o "-p $PORT -c listen_addresses=127.0.0.1 -c unix_socket_directories=''" start
"$PGB/createdb" -h 127.0.0.1 -p $PORT -U vipphone vipphone_test
export TEST_DATABASE_URL="postgresql+psycopg://vipphone@127.0.0.1:$PORT/vipphone_test"
make test
```

Hai bẫy đã gặp thật khi dựng cụm này, ghi ra để không mất thời gian lại:

1. `initdb` báo *"invalid locale settings"* nếu `LANG`/`LC_*` của shell là tiếng
   Việt — phải đặt `LANG=C LC_ALL=C` và `--locale=C`.
2. PostgreSQL **không khởi động** được nếu thư mục socket dài quá 103 byte
   (đường dẫn scratchpad của phiên dài hơn thế). Cách vá: `unix_socket_directories=''`
   rồi nối bằng TCP.

---

## 3. Bố cục trên máy chủ

```
<APP_ROOT>/<môi trường>/
├── releases/<release_id>/     mã của từng bản phát hành (+ release.json)
├── current  →  releases/…     bản ĐANG CHẠY
├── previous →  releases/…     bản TRƯỚC (đích của rollback)
├── shared/.env                SECRET — người đặt, script KHÔNG tạo, KHÔNG in
├── backups/<mốc>/             sao lưu CSDL + metadata
└── history.log                sổ triển khai, chỉ ghi thêm
```

`release_id` dạng `YYYYMMDD-HHMMSS-<7 ký tự sha>`, ví dụ `20261007-182500-a31df21`.

**Vì sao `$HOME` mà không phải `/opt/vip/vipphone`:** user `deploy` trên host
staging **không có sudo** (`docs/MASTER_STATUS.md` §31.1), nên nó không ghi được
vào `/opt`. Cấu trúc giữ nguyên. Máy chủ nào có sudo thì đặt
`APP_ROOT=/opt/vip/vipphone` trong `deploy/deploy.local.conf`.

**Việc làm một lần, do người làm, KHÔNG do script:**

1. tạo container PostgreSQL của môi trường (`vipphone-staging-pg` / `vipphone-prod-pg`)
   và network tương ứng;
2. đặt `<APP_ROOT>/<môi trường>/shared/.env` theo hợp đồng ở `docs/staging.md`.

Script triển khai **từ chối chạy** nếu thiếu một trong hai — nó không tự tạo
database và không tự sinh secret.

---

## 4. Triển khai staging — từng bước script làm gì

1. cây làm việc sạch · lấy SHA · sinh `release_id`
2. chạy ruff + toàn bộ pytest **tại máy**
3. `git archive HEAD` → gói `.tar.gz` (nên **không thể** lẫn file chưa commit)
4. ghi sổ artifact (mã băm gói) → production sau này đòi trùng băm
5. đưa gói lên, **kiểm sha256 ở phía máy chủ** trước khi giải nén
6. sao lưu CSDL staging
7. `alembic upgrade head` + `alembic check` bằng **ảnh của chính bản đó**
8. chạy bản mới dưới **tên tạm, cổng tạm**
9. health check bản tạm — **hỏng thì gỡ container tạm, bản đang chạy không bị đụng**
10. đổi `current`, bản cũ thành `previous`
11. ghi `release.json`, dọn bản cũ (giữ `KEEP_RELEASES`)

---

## 5. Sao lưu

`./deploy/backup.sh <môi trường>` lưu bốn thứ vào `<APP_ROOT>/<env>/backups/<mốc>/`:

| | |
|---|---|
| CSDL | `pg_dump -Fc`, kèm `.sha256`, **và kiểm `pg_restore --list` đọc được** |
| dữ liệu bền | `shared/data/` nếu có |
| cấu hình | **chỉ TÊN biến** trong `shared/.env` (`env-keys.txt`) |
| metadata | `release.json` của bản đang chạy + 50 dòng cuối `history.log` |

Hai điều cố ý:

- **Giá trị secret KHÔNG được sao lưu ở đây.** Sao lưu secret phải là việc có
  chủ ý, có nơi cất riêng — không lẫn vào bản sao lưu chạy tự động.
- **Kiểm dump đọc được, không chỉ kiểm file tồn tại.** Một dump hỏng vẫn là một
  file có kích thước, và sẽ chỉ lộ ra đúng lúc cần phục hồi.

**Giới hạn còn nguyên:** bản sao lưu nằm **trên chính máy chủ đó**. Mất máy là
mất cả CSDL lẫn bản sao lưu. Đưa ra khỏi máy là việc chưa làm — xem
`docs/backup-restore.md`.

---

## 6. Rollback và database

`./deploy/rollback.sh <môi trường>` quay `current` về `previous`, chạy lại ảnh của
bản đó, health check, rồi **xác nhận `current` đúng là bản đích** (không xác nhận
được thì báo chưa xong).

> **Rollback này quay lại MÃ, KHÔNG quay lại LƯỢC ĐỒ DATABASE. Cố ý.**
>
> `alembic downgrade` chỉ an toàn khi chính migration đó được **viết** để đảo
> ngược được — và không thể suy ra điều đó từ việc hàm `downgrade()` có tồn tại.
> Hạ cấp sai thì **mất dữ liệu**, mà không rollback nào vá lại được.
>
> Vì vậy luật là **migration tương thích ngược**: mã cũ phải chạy được trên lược
> đồ mới. Cụ thể là thêm cột cho phép NULL (hoặc có default), không xoá/đổi tên
> cột đang được mã cũ dùng trong cùng một lượt, và tách việc xoá cột sang một
> lượt sau khi không còn bản nào dùng nó.
>
> `production.sh` đếm số file migration mới so với bản đang chạy và **báo ra**
> khi có. `rollback.sh` cũng báo khi bản đích có ít migration hơn bản đang chạy.
> Hai chỗ đó báo, chứ không tự xử — vì quyết định này không suy ra được từ số file.

---

## 7. Đồng bộ GitHub

Sau khi production đã nghiệm thu:

```bash
git push origin HEAD
git tag -a "v<release_id>" -m "release <release_id>" && git push origin --tags
```

**Push lỗi KHÔNG làm lượt triển khai thành lỗi**, nếu bản đang chạy đã được xác
minh. Nhưng phải báo `GITHUB_SYNC_PENDING = YES` và **không được để lịch sử local
mất** — nhánh vẫn còn, tag vẫn còn, đẩy lại khi mạng/quyền trở lại.

**Secret:** không commit `.env`; không đưa token/mật khẩu/khoá riêng lên GitHub.
Secret nằm ở `shared/.env` **trên máy chủ**. Không script nào trong `deploy/`
đọc secret về máy trạm hay in nó ra — có ca thử chốt điều này.

---

## 8. GitHub Actions — giữ gì, bỏ gì

Rà ngày 07/10/2026. Repo có **một** workflow: `.github/workflows/ci.yml`, 5 job.

| Job | Phân loại | Quyết định |
|---|---|---|
| `secret-scan` (gitleaks, toàn bộ lịch sử) | **A — giữ** | rẻ, bắt thứ không ai bắt lại được sau khi đã push |
| `validate-static` (12 guard: tiền hiển thị, QR, CSP, khoá Turnstile…) | **A — giữ** | rẻ, và mỗi guard tương ứng một lỗi đã xảy ra thật |
| `backend` (ruff + alembic + pytest, PostgreSQL service) | **A — giữ** | lưới an toàn cho mã vào develop/main |
| `dependency-scan` (pip-audit) | **A — giữ** | rẻ |
| `e2e` (**3 engine** × Playwright + PostgreSQL) | **B — chuyển sang chạy tay** | job tốn nhất; `if: github.event_name == 'workflow_dispatch'` |

Thêm một thay đổi về **trùng lặp**: `on: push:` trần làm mọi nhánh có PR mở chạy
trọn bộ CI **hai lần** cho cùng một commit. Nay `push` chỉ còn `develop` và `main`;
`pull_request` giữ nguyên. Độ phủ không giảm, phần trùng thì mất.

**Không workflow nào bị xoá. Không workflow nào bị disable.** `e2e` chạy lại bất
cứ lúc nào: tab Actions → CI → Run workflow. Bật lại vĩnh viễn: xoá dòng `if:`.

> ⚠️ **Phải biết trước khi bật branch protection.** `scripts/enable_branch_protection.sh`
> liệt kê ba check `E2E (chromium|firefox|webkit)` là **bắt buộc**. Ba check đó nay
> không xuất hiện trên PR nữa, nên bật protection với danh sách cũ sẽ làm PR
> **chờ mãi một check không bao giờ tới**. Sửa danh sách trước, hoặc bỏ dòng `if:`.
> Đây là việc còn mở, chưa làm trong lượt này.

---

## 9. Vì sao lượt này CHƯA deploy staging thật

Hai điều **đo được**, không phải phỏng đoán:

1. **Máy này (Mac mini) không có khoá SSH của host staging.** `ls ~/.ssh` không có
   `*staging*` nào. `docs/MASTER_STATUS.md` §30.2 ghi đúng điều này: khoá
   `vip_viettelpost_staging_admin/_deploy` được tạo **trên MacBook**.
2. **Máy này không có Docker** (`command -v docker` trống), nên cũng không build
   thử được ảnh tại máy — ca `test_dockerfile_build_duoc` bị **skip**, và việc bị
   skip được in ra chứ không im lặng thành "đạt".

Cần đúng ba thứ để chạy được `./deploy/staging.sh` thật:

| Cần | Ai làm |
|---|---|
| khoá SSH vào host staging, đặt trên **máy sắp chạy deploy** | Owner (hoặc chép từ MacBook) |
| `deploy/deploy.local.conf` điền host/user/khoá/URL | một lệnh, xem `deploy.local.conf.example` |
| container PostgreSQL + `shared/.env` trên host | người, một lần, xem §3 |

Có ba thứ đó thì `READY_FOR_STAGING = YES` chuyển thành một lượt chạy thật.

---

## 10. Gỡ lỗi

| Triệu chứng | Nhìn trước tiên |
|---|---|
| `DỪNG: cây làm việc KHÔNG sạch` | `git status`. Script **không** stash hộ, cố ý |
| `test tại máy KHÔNG đạt` | đặt `TEST_DATABASE_URL` chưa? xem §2 |
| `require_host` dừng | `deploy/deploy.local.conf` — xem §9 |
| `thiếu shared/.env` | đặt trên **máy chủ**, không phải máy trạm |
| health không lên 200 | `docker logs --tail 50 vipphone-<env>-app`; `RestartCount > 0` nghĩa là nó **đang chết rồi tự dựng lại** |
| `không có phiếu staging PASS nào cho SHA` | chạy `verify.sh staging` trên đúng commit đó |
| `mã băm gói LỆCH` | HEAD đã khác so với bản đã nghiệm thu ⇒ staging lại |
| `pg_restore --list KHÔNG đọc được` | bản dump hỏng. **Đừng deploy tiếp** |

Nguyên tắc khi deploy hỏng: **không sửa trực tiếp trên production**. Rollback →
sửa ở máy → test → staging → deploy lại.
