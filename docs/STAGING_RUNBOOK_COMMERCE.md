# RUNBOOK — Deploy + nghiệm thu thương mại trên STAGING thật

Dành cho **máy có khoá SSH vào staging** (MacBook của Owner, hoặc một phiên harness được cấp mạng + khoá).
Mỗi bước ghi **bằng chứng cần dán lại**. Bước nào FAIL ⇒ dừng, dán output, không "sửa tay" trên máy chủ.

> Phiên harness cloud (2026-10-07/08) **không** chạy được runbook này: `curl https://qua.viporder.vn` ⇒
> `CONNECT tunnel failed, response 403`; TCP `160.22.170.20:22` bị chặn; không có khoá SSH. Xem D-006.

| | |
|---|---|
| Staging | `160.22.170.20` · user `deploy` · `https://qua.viporder.vn` · container `vipphone-staging-app` (18080) + `vipphone-staging-pg` · db `vipphone_staging` |
| Production | `160.22.171.228` — **CẤM ĐỤNG**. `deploy/common.sh` từ chối nếu `STAGING_HOST` là host này (chốt SAI HOST). |
| Cần trên máy trạm | repo sạch ở `develop`, `.venv` đủ `requirements-dev.txt`, `playwright install chromium firefox webkit`, Docker (bước test của `staging.sh`) |

## 0. Đồng bộ + chốt danh tính (BẮT BUỘC trước mọi thứ)

```bash
git fetch origin && git checkout develop && git pull --ff-only
git rev-parse HEAD                      # dán: phải bằng SHA develop mới nhất, CI xanh
git status --porcelain                  # dán: phải RỖNG
cp -n deploy/deploy.local.conf.example deploy/deploy.local.conf   # điền: STAGING_HOST=160.22.170.20,
#   STAGING_USER=deploy, STAGING_SSH_KEY=<đường dẫn khoá>, STAGING_URL=https://qua.viporder.vn

ssh -i <khoá> deploy@160.22.170.20 '
  hostname; hostname -I; . /etc/os-release; echo "$PRETTY_NAME"
  docker ps --format "{{.Names}}  {{.Image}}  {{.Status}}  {{.Ports}}" | grep vipphone
  docker exec vipphone-staging-pg psql -U vipphone -d vipphone_staging -Atc \
    "select current_database(), (select version_num from alembic_version), (select count(*) from information_schema.tables where table_schema=current_schema())"
  docker inspect -f "{{.Config.Image}} restart={{.RestartCount}}" vipphone-staging-app'
```

Phải thấy: IP `160.22.170.20` (KHÔNG `160.22.171.228`), db `vipphone_staging`. Nhập nhằng ⇒ **DỪNG**.
Ghi lại: `STAGING SHA BEFORE` (tag image), migration head trước, số bảng trước.

## 0b. Đo trước lượt đầu (đã đo 2026-10-08 trên máy chủ)

Đo được: IP `160.22.170.20` ✔ · app `vipphone-staging:c9ab9d1…` (G14, PR #62) · DB `vipphone_staging` ở
`0007_product_catalog`, 11 bảng · `.env` cũ ở `~/vipphone-staging/.env` (9 biến) · `~/vip/vipphone/staging` chưa có.

Lượt đầu sẽ: migration `0007 → 0014` (thuần thêm, mã G14 vẫn chạy được trong lúc chờ), đổi container cũ thành
`vipphone-staging-app-prev-<giây>` **đã dừng**, và bản mới nghe ở `127.0.0.1:18080` (bản cũ nghe `0.0.0.0:18080`).
Ba điều PHẢI đúng trước khi chạy `staging.sh` — lệnh chỉ đọc:

```bash
ssh … '
  echo "== ai phục vụ qua.viporder.vn?"; ss -ltnp 2>/dev/null | grep -E ":(80|443|18080|18081) " ; docker ps --format "{{.Names}} {{.Ports}}" | grep -E ":(80|443)->" || true
  echo "== mạng của pg + app"; for c in vipphone-staging-pg vipphone-staging-app; do docker inspect -f "$c {{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}} {{end}}" $c; done
  echo "== host trong DATABASE_URL (KHÔNG in mật khẩu)"; sed -n "s#^DATABASE_URL=.*@\([^/:]*\).*#\1#p" ~/vipphone-staging/.env'
```

1. Reverse proxy phải tới app qua `127.0.0.1:18080` (proxy chạy trên host). Nếu proxy là container nối qua
   `172.17.0.1:18080` thì bản mới **không tới được** ⇒ DỪNG, báo lại.
2. `vipphone-staging-pg` nằm trong mạng `vipphone-staging-net`, và host trong `DATABASE_URL` là `vipphone-staging-pg`.
3. Cổng `18081` (cổng tạm) trống.

Bộ test tại máy của `staging.sh` cần PostgreSQL sống: đặt `TEST_DATABASE_URL` theo `docs/DIRECT-DEPLOY.md` §2.

**Quay về khẩn cấp ở lượt đầu** (lúc này `rollback.sh` chưa có `previous`): bản G14 vẫn còn, chỉ bị dừng —
`docker rm -f vipphone-staging-app && docker rename vipphone-staging-app-prev-<giây> vipphone-staging-app && docker start vipphone-staging-app`.
Lược đồ đã ở 0014 nhưng thuần thêm ⇒ mã G14 chạy được.

## 1. Chuyển cấu hình sang bố cục của script mới (một lần)

Script mới đọc `~/vip/vipphone/staging/shared/.env` (chưa từng tồn tại ở cách deploy cũ ⇒ lần đầu `staging.sh`
sẽ dừng ở `require_shared_env` — đúng thiết kế). Trên máy chủ, **không in giá trị**:

```bash
ssh -i <khoá> deploy@160.22.170.20
mkdir -p ~/vip/vipphone/staging/shared && chmod 700 ~/vip/vipphone/staging/shared
# Chép file .env đang dùng (đường dẫn của lượt deploy cũ, ví dụ ~/vipphone-staging/.env) sang:
cp <file .env đang dùng> ~/vip/vipphone/staging/shared/.env && chmod 600 ~/vip/vipphone/staging/shared/.env
# Biến MỚI cho thương mại (xem .env.staging.example, mục THƯƠNG MẠI):
echo "PAYMENT_MOCK_WEBHOOK_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" >> ~/vip/vipphone/staging/shared/.env
echo 'BANK_TRANSFER_INSTRUCTIONS=[THỬ - STAGING] Không chuyển tiền thật. Tài khoản thật do Owner cung cấp (D-009).' >> ~/vip/vipphone/staging/shared/.env
grep -oE '^[A-Z_]+' ~/vip/vipphone/staging/shared/.env | sort      # dán: CHỈ tên biến
```

Giữ `PAYMENT_MOCK_WEBHOOK_SECRET` cho bước 5 (đọc bằng `ssh … 'grep ^PAYMENT_MOCK ~/vip/…/.env | cut -d= -f2-'`
vào biến môi trường của máy trạm — không dán vào chat/tài liệu).

## 2. Đối chứng âm các cửa khoá (an toàn, không đụng máy chủ)

```bash
bash deploy/tests/thu-deploy.sh | tail -1                       # dán: 71 đạt · 0 không đạt (gồm SAI HOST)
bash deploy/tests/thu-promote-docker.sh | tail -1               # dán: 12 đạt (Docker thật; không có Docker ⇒ BỎ QUA)
# sai host: staging trỏ vào production ⇒ phải DỪNG trước khi SSH
bash -c '. deploy/common.sh; load_conf; STAGING_HOST=160.22.171.228; select_env staging; require_host'; echo "exit=$?"
# cây bẩn ⇒ staging.sh phải DỪNG ở bước 1
touch _ban.txt && ./deploy/staging.sh; echo "exit=$?"; rm _ban.txt
# production khi chưa có phiếu staging cho đúng SHA ⇒ phải DỪNG
./deploy/production.sh; echo "exit=$?"            # KHÔNG có PRODUCTION_HOST thì càng dừng sớm
```

## 3. Preflight + DEPLOY (lần chạy THẬT đầu tiên của script mới)

```bash
./deploy/staging.sh 2>&1 | tee staging-deploy.log    # gồm: test tại máy → đóng gói → backup → migration
                                                     #      (upgrade + alembic check) → chạy tạm → health → đổi
./deploy/verify.sh staging 2>&1 | tee staging-verify.log   # băm mã trên máy chủ == cây commit, health, ready
ssh … 'docker run --rm --network vipphone-staging-net --env-file ~/vip/vipphone/staging/shared/.env \
       vipphone-staging:$(readlink ~/vip/vipphone/staging/current | xargs basename) \
       python scripts/staging_preflight.py' | tee staging-preflight.log
```

Dán: kích thước + thời gian bản backup (bước 5 của `staging.sh`), `alembic current/heads/check`, RELEASE_ID,
`GIT_SHA`, health/ready 200, `RestartCount`. Kỳ vọng head `0014_order_attribution`, 24 bảng.

## 4. Nghiệm thu chức năng — API thật (dữ liệu có marker)

```bash
STAFF_KEY=<khoá nhân viên staging> MOCK_SECRET=<bước 1> \
  .venv/bin/python scripts/staging_commerce_smoke.py --base-url https://qua.viporder.vn --i-know-this-is-staging \
  | tee staging-commerce-smoke.log                    # 24 bước: G15, G16 + idempotency, IDOR, G17 COD/CK/webhook,
                                                      # kho, giá + lịch sử, attribution, quà, huỷ nhả hàng
bash scripts/staging_acceptance.sh remote https://qua.viporder.vn | tee staging-gift-regression.log   # funnel quà cũ
```

## 5. Trình duyệt thật × 3 engine × 4 độ rộng (chỉ đọc)

```bash
.venv/bin/python scripts/staging_browser_check.py --base-url https://qua.viporder.vn \
  | tee staging-browser.log      # chromium/firefox/webkit × 320/375/390/430: tràn ngang, console, asset hỏng, mixed content
```

## 6. Tải nhẹ

```bash
.venv/bin/python scripts/load_smoke.py --base-url https://qua.viporder.vn --concurrency 8 --duration 30 \
  --staff-key "$STAFF_KEY" | tee staging-load.log
ssh … 'docker stats --no-stream vipphone-staging-app vipphone-staging-pg;
       docker exec vipphone-staging-pg psql -U vipphone -d vipphone_staging -Atc "select count(*) from pg_stat_activity";
       docker inspect -f "restart={{.RestartCount}}" vipphone-staging-app'
```

429 do rate limit là chủ ý — tách riêng, không tính lỗi máy chủ.

## 7. Sao lưu sau hoạt động + phục hồi vào DB tạm (KHÔNG đè DB đang chạy)

```bash
./deploy/backup.sh staging | tee staging-backup-after.log
ssh … 'cd ~/vip/vipphone/staging/current && python3 -I scripts/restore_drill.py \
        --docker-pg vipphone-staging-pg --db vipphone_staging --user vipphone' | tee staging-restore.log
```

`restore_drill.py --docker-pg` chỉ cần `python3` hệ thống (đã chạy thử trên container `postgres:16` giả lập
staging tại máy: 24/24 bảng khớp md5; đối chứng âm làm hỏng 1 cột ⇒ FAIL đúng).

## 8. Rollback thật (chỉ mã — schema additive, không downgrade)

```bash
./deploy/rollback.sh staging | tee staging-rollback.log        # B → A; script in bản/SHA đang chạy
curl -s https://qua.viporder.vn/api/health; curl -s -o /dev/null -w '%{http_code}\n' https://qua.viporder.vn/
./deploy/staging.sh && ./deploy/verify.sh staging              # A → B (đưa lại develop)
```

Ghi chú ranh giới: lượt đầu dùng script mới, "bản trước" là container cũ đổi tên `vipphone-staging-app-prev-*`;
nếu `rollback.sh` báo không có `previous` thì chạy `staging.sh` hai lần (bản B lần 1 rồi B' cùng SHA) **không**
chứng minh được gì — khi đó ghi `ROLLBACK = NOT PROVEN` thay vì PASS. Mã G17 đã được chứng minh chạy trên schema
`0014` (12/12 khói, tại máy) nên quay về bản cũ hơn là an toàn với schema.

## 9. Log + dọn dữ liệu thử

```bash
ssh … 'docker logs --since 2h vipphone-staging-app 2>&1 | grep -cE "Traceback|deadlock|timeout|too many connections";
       docker logs --since 2h vipphone-staging-app 2>&1 | grep -cE "0[35789][0-9]{8}|PAYMENT_MOCK|DATABASE_URL|password"'   # cả hai phải 0
ssh … 'docker run --rm --network vipphone-staging-net --env-file ~/vip/vipphone/staging/shared/.env \
       vipphone-staging:<RELEASE_ID> python scripts/cleanup_test_data.py'            # đếm
ssh … '… python scripts/cleanup_test_data.py --apply'                              # xoá, tự kiểm lại
```

## 10. Gửi lại

Toàn bộ các tệp `staging-*.log` (đã không chứa secret). Harness điền `docs/OWNER_ACCEPTANCE_COMMERCE.md` và
`docs/MASTER_STATUS.md` từ đó và kết luận `READY_FOR_OWNER_ACCEPTANCE`.
