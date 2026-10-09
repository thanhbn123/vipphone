#!/usr/bin/env bash
# =============================================================================
# CHẠY TOÀN BỘ RUNBOOK STAGING BẰNG MỘT LỆNH — từ máy trạm của Owner.
#   bash scripts/owner_staging_run.sh
# =============================================================================
# Làm đúng các bước của docs/STAGING_RUNBOOK_COMMERCE.md theo thứ tự, mỗi bước một
# tệp log trong staging-run-<thời điểm>/, và DỪNG ở bước hỏng đầu tiên. Gửi lại cả
# thư mục đó (không chứa secret: giá trị secret bị thay bằng *** trước khi kết thúc).
#
# Cửa khoá (dừng TRƯỚC khi đụng máy chủ nếu sai):
#   · danh tính máy chủ: IP phải là EXPECT_IP (160.22.170.20), KHÔNG phải production
#   · database phải là vipphone_staging
#   · Caddy phải chuyển qua.viporder.vn tới localhost/127.0.0.1:18080 — bản mới
#     chỉ nghe ở 127.0.0.1; trỏ nơi khác thì trang sẽ không tới được app
#
# KHÔNG: đụng production, in secret, tự sửa gì trên máy chủ ngoài những gì
# deploy/*.sh làm, xoá dữ liệu không có marker. Chạy được với bash 3.2 (macOS).
# =============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 2
[ -f deploy/deploy.local.conf ] || { echo "DỪNG: thiếu deploy/deploy.local.conf (xem runbook mục 0)." >&2; exit 2; }
# shellcheck disable=SC1091
. deploy/deploy.conf; . deploy/deploy.local.conf

EXPECT_IP="${EXPECT_IP:-160.22.170.20}"
FORBIDDEN_IP="160.22.171.228"
BASE="${STAGING_BASE_URL:-${STAGING_URL:-}}"
KEY="${STAGING_SSH_KEY/#\~/$HOME}"
PY="$REPO/.venv/bin/python"
APP=vipphone-staging-app; PG=vipphone-staging-pg; DB=vipphone_staging; NET=vipphone-staging-net
ROOT_R='~/vip/vipphone/staging'
OUT="$REPO/staging-run-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
SUMMARY="$OUT/00-TOM-TAT.txt"

[ "${STAGING_HOST:-}" = "$EXPECT_IP" ] || { echo "DỪNG: STAGING_HOST='${STAGING_HOST:-}' ≠ $EXPECT_IP" >&2; exit 2; }
[ -n "$BASE" ] || { echo "DỪNG: thiếu STAGING_URL trong deploy/deploy.local.conf" >&2; exit 2; }
[ -x "$PY" ] || { echo "DỪNG: thiếu $PY — tạo .venv và cài requirements-dev.txt (runbook mục 0)." >&2; exit 2; }

rsh() { ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$KEY" "$STAGING_USER@$STAGING_HOST" "$1"; }

# step <tên> <lệnh...>: chạy, ghi log, ghi tóm tắt; hỏng thì dừng cả lượt.
step() {
  local name="$1"; shift
  printf '▶ %-28s ' "$name"
  "$@" > "$OUT/$name.log" 2>&1
  local code=$?
  local last; last="$(grep -hE 'KẾT QUẢ|TỔNG|DỪNG|RELEASE_ID|PASS —|FAIL —' "$OUT/$name.log" | tail -1)"
  printf '%-4s %s\n' "$([ $code = 0 ] && echo OK || echo HỎNG)" "$last" | tee -a "$SUMMARY" >/dev/null
  if [ $code = 0 ]; then echo "OK   $last"; else echo "HỎNG (mã $code) — xem $OUT/$name.log"; finish 1; fi
}
# expect_fail <tên> <lệnh...>: đối chứng âm — lệnh PHẢI thất bại.
expect_fail() {
  local name="$1"; shift
  printf '▶ %-28s ' "$name"
  "$@" > "$OUT/$name.log" 2>&1
  local code=$?
  if [ $code != 0 ]; then echo "OK   (dừng đúng, mã $code)"; echo "OK   $name dừng đúng" >> "$SUMMARY"
  else echo "HỎNG — lệnh lẽ ra phải DỪNG"; echo "HỎNG $name KHÔNG dừng" >> "$SUMMARY"; finish 1; fi
}

SECRETS=()
finish() {
  # Thay mọi giá trị secret đã đọc trong lượt này bằng *** trong toàn bộ log.
  local f s
  for f in "$OUT"/*.log; do
    [ -f "$f" ] || continue
    for s in "${SECRETS[@]:-}"; do
      [ -n "$s" ] || continue
      S="$s" "$PY" -c 'import os,sys;p=sys.argv[1];t=open(p,encoding="utf-8",errors="replace").read();open(p,"w",encoding="utf-8").write(t.replace(os.environ["S"],"***"))' "$f"
    done
  done
  echo
  echo "=== Tóm tắt: $SUMMARY"; cat "$SUMMARY"
  echo "=== Gửi lại cả thư mục: $OUT"
  exit "$1"
}

echo "=== RUNBOOK STAGING · $(date) · $(git rev-parse --short HEAD) → $BASE"
{ echo "develop: $(git rev-parse HEAD)"; echo "đích: $STAGING_USER@$STAGING_HOST · $BASE"; } > "$SUMMARY"

# ---------------------------------------------------------------- 0. cửa khoá
check_identity() {
  rsh "hostname; hostname -I; docker exec $PG psql -U vipphone -d $DB -Atc 'select current_database(), (select version_num from alembic_version)'; docker inspect -f '{{.Config.Image}}' $APP" \
    > "$OUT/00-danh-tinh.raw" 2>&1 || { cat "$OUT/00-danh-tinh.raw"; return 1; }
  cat "$OUT/00-danh-tinh.raw"
  grep -qw "$EXPECT_IP" "$OUT/00-danh-tinh.raw" || { echo "DỪNG: máy chủ không có IP $EXPECT_IP"; return 1; }
  ! grep -qw "$FORBIDDEN_IP" "$OUT/00-danh-tinh.raw" || { echo "DỪNG: đây là PRODUCTION"; return 1; }
  grep -q "^$DB|" "$OUT/00-danh-tinh.raw" || { echo "DỪNG: database không phải $DB"; return 1; }
  echo "KẾT QUẢ: danh tính đúng — $EXPECT_IP, $DB"
}
check_caddy() {
  local host up src
  host="$(printf '%s' "$BASE" | sed -E 's#^[a-z]+://##; s#[:/].*$##')"
  # Đường 1: Caddyfile trên host (chỉ khi user deploy đọc được). Phân biệt
  # "không tồn tại" với "không có quyền" — hai nguyên nhân, hai cách xử (#93).
  if rsh "cat /etc/caddy/Caddyfile" > "$OUT/00-caddy.raw" 2>"$OUT/00-caddy.err"; then
    src=Caddyfile
    up="$(awk -v h="$host" '
      index($0, h) && /\{/ {inb=1; d=0}
      inb { n=gsub(/\{/,"{"); m=gsub(/\}/,"}"); d+=n-m; if ($1=="reverse_proxy") {print $2} if (d<=0 && NR>1 && m>0) inb=0 }' "$OUT/00-caddy.raw" | head -1)"
  else
    grep -q 'No such file' "$OUT/00-caddy.err" && echo "/etc/caddy/Caddyfile không tồn tại trên host (Caddy có thể chạy trong container)" \
                                                || echo "/etc/caddy/Caddyfile: $(tr -d '\n' < "$OUT/00-caddy.err")"
    # Đường 2: Caddy admin API (localhost:2019) — đo 2026-10-10: user deploy đọc được,
    # không cần sudo; Caddy staging chạy trong container net=host nên 127.0.0.1 là host.
    if rsh "curl -s --max-time 5 http://localhost:2019/config/" > "$OUT/00-caddy.raw" 2>/dev/null && [ -s "$OUT/00-caddy.raw" ]; then
      src="admin API"
      up="$("$PY" - "$host" "$OUT/00-caddy.raw" <<'PY'
import json, sys
host, path = sys.argv[1], sys.argv[2]
cfg = json.load(open(path, encoding="utf-8"))
def walk(o, hit):
    if isinstance(o, dict):
        if o.get("handler") == "reverse_proxy" and hit:
            for u in o.get("upstreams", []):
                if "dial" in u: print(u["dial"]); return True
        if "match" in o and any(host in m.get("host", []) for m in o["match"] if isinstance(m, dict)):
            hit = True
        for v in o.values():
            if walk(v, hit): return True
    elif isinstance(o, list):
        for v in o:
            if walk(v, hit): return True
    return False
walk(cfg, False)
PY
)"
    fi
  fi
  if [ -z "${src:-}" ]; then
    if [ "${CADDY_UPSTREAM_CONFIRMED:-}" = "localhost:$STAGING_PORT" ]; then
      echo "KẾT QUẢ: không đọc được Caddyfile lẫn admin API; Owner đã tự xác nhận upstream = localhost:$STAGING_PORT"
      return 0
    fi
    echo "DỪNG: không đọc được Caddyfile (host) lẫn Caddy admin API (localhost:2019). Owner xem bằng quyền root:"
    echo "      sudo grep -rn -A8 $host /etc/caddy/Caddyfile /srv/*/Caddyfile"
    echo "      nếu reverse_proxy là localhost:$STAGING_PORT hoặc 127.0.0.1:$STAGING_PORT thì chạy lại với"
    echo "      CADDY_UPSTREAM_CONFIRMED=localhost:$STAGING_PORT bash scripts/owner_staging_run.sh"
    return 1
  fi
  echo "Caddy ($src): $host → ${up:-(không tìm thấy reverse_proxy)}"
  case "$up" in
    localhost:"$STAGING_PORT"|127.0.0.1:"$STAGING_PORT"|http://localhost:"$STAGING_PORT"|http://127.0.0.1:"$STAGING_PORT")
      echo "KẾT QUẢ: Caddy ($src) tới app qua $up — bản mới nghe 127.0.0.1:$STAGING_PORT là đúng" ;;
    *) echo "DỪNG: Caddy trỏ '${up:-?}', không phải localhost:$STAGING_PORT — bản mới (127.0.0.1) sẽ không tới được. Báo lại harness."; return 1 ;;
  esac
}
step 00-danh-tinh check_identity
step 00-caddy check_caddy

# ------------------------------------------------- 1. cấu hình bố cục mới (một lần)
migrate_env() {
  rsh "set -eu
R=$ROOT_R; mkdir -p \$R/shared && chmod 700 \$R/shared
if [ ! -f \$R/shared/.env ]; then
  [ -f ~/vipphone-staging/.env ] || { echo 'DỪNG: không có ~/vipphone-staging/.env để chép'; exit 1; }
  cp ~/vipphone-staging/.env \$R/shared/.env && chmod 600 \$R/shared/.env && echo 'đã chép .env cũ'
else echo 'shared/.env đã có — giữ nguyên'; fi
grep -q '^PAYMENT_MOCK_WEBHOOK_SECRET=' \$R/shared/.env || { echo \"PAYMENT_MOCK_WEBHOOK_SECRET=\$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')\" >> \$R/shared/.env; echo 'đã sinh khoá webhook giả lập TRÊN máy chủ'; }
grep -q '^BANK_TRANSFER_INSTRUCTIONS=' \$R/shared/.env || { echo 'BANK_TRANSFER_INSTRUCTIONS=[THỬ - STAGING] Không chuyển tiền thật. Tài khoản thật do Owner cung cấp (D-009).' >> \$R/shared/.env; echo 'đã thêm hướng dẫn chuyển khoản [THỬ]'; }
echo '--- tên biến (không giá trị):'; grep -oE '^[A-Z_]+' \$R/shared/.env | sort | tr '\n' ' '; echo
echo 'KẾT QUẢ: shared/.env sẵn sàng'"
}
step 01-cau-hinh migrate_env

# ------------------------------------------------- 2. đối chứng âm (không đụng máy chủ)
step        02-thu-deploy   bash deploy/tests/thu-deploy.sh
expect_fail 02-sai-host     bash -c ". deploy/common.sh; load_conf; STAGING_HOST=$FORBIDDEN_IP; select_env staging; require_host"
touch _cay_ban_thu.txt
expect_fail 02-cay-ban      ./deploy/staging.sh
rm -f _cay_ban_thu.txt
expect_fail 02-production   ./deploy/production.sh

# ------------------------------------------------- 3. deploy + nghiệm thu
if [ -z "${TEST_DATABASE_URL:-}" ] && [ -x /opt/homebrew/opt/postgresql@16/bin/pg_ctl ]; then
  export TEST_DATABASE_URL="postgresql+psycopg://vipphone@127.0.0.1:55517/vipphone_test"
  echo "(dùng PostgreSQL tạm ở 127.0.0.1:55517 cho test tại máy — runbook mục 0, bước 3)"
fi
step 03-staging     ./deploy/staging.sh
step 03-verify      ./deploy/verify.sh staging
preflight() {
  rsh "R=$ROOT_R; docker run --rm --network $NET --env-file \$R/shared/.env vipphone-staging:\$(readlink \$R/current | xargs basename) python scripts/staging_preflight.py"
  return 0  # preflight có WARN chủ ý (D-008, Turnstile); đọc log, không chặn lượt
}
step 03-preflight   preflight

# ------------------------------------------------- 4. chức năng thật
STAFF_KEY="$(rsh "grep '^STAFF_API_KEYS=' $ROOT_R/shared/.env | cut -d= -f2- | cut -d, -f1")"
MOCK_SECRET="$(rsh "grep '^PAYMENT_MOCK_WEBHOOK_SECRET=' $ROOT_R/shared/.env | cut -d= -f2-")"
SECRETS=("$STAFF_KEY" "$MOCK_SECRET")
export STAFF_KEY MOCK_SECRET
step 04-smoke-thuong-mai "$PY" scripts/staging_commerce_smoke.py --base-url "$BASE" --i-know-this-is-staging
step 04-hoi-quy-qua      bash scripts/staging_acceptance.sh remote "$BASE"

# ------------------------------------------------- 5–6. trình duyệt + tải
# BROWSERS chỉ để diễn tập trên máy thiếu engine; mặc định đủ 3 engine.
step 05-trinh-duyet "$PY" scripts/staging_browser_check.py --base-url "$BASE" --browsers "${BROWSERS:-chromium,firefox,webkit}"
step 06-tai-nhe     "$PY" scripts/load_smoke.py --base-url "$BASE" --concurrency 8 --duration 30 --staff-key "$STAFF_KEY"
step 06-tai-sau     rsh "docker stats --no-stream $APP $PG; docker inspect -f 'restart={{.RestartCount}}' $APP"

# ------------------------------------------------- 7. sao lưu + phục hồi DB tạm
step 07-sao-luu     ./deploy/backup.sh staging
step 07-phuc-hoi    rsh "cd $ROOT_R/current && python3 -I scripts/restore_drill.py --docker-pg $PG --db $DB --user vipphone"

# ------------------------------------------------- 8. rollback thật (cơ chế; cùng SHA)
step 08-staging-2   ./deploy/staging.sh
step 08-rollback    ./deploy/rollback.sh staging
step 08-verify-rb   ./deploy/verify.sh staging
step 08-staging-3   ./deploy/staging.sh
step 08-verify-3    ./deploy/verify.sh staging

# ------------------------------------------------- 9. log + dọn dữ liệu thử
log_check() {
  local err pii
  err="$(rsh "docker logs --since 3h $APP 2>&1 | grep -cE 'Traceback|deadlock|too many connections' || true")"
  pii="$(rsh "docker logs --since 3h $APP 2>&1 | grep -cE '0[35789][0-9]{8}|PAYMENT_MOCK|DATABASE_URL|password' || true")"
  echo "dòng lỗi: $err · dòng PII/secret: $pii"
  [ "$err" = 0 ] && [ "$pii" = 0 ] && echo "KẾT QUẢ: log sạch" || { echo "KẾT QUẢ: log có vấn đề"; return 1; }
}
step 09-log log_check
cleanup() {
  rsh "R=$ROOT_R; docker run --rm --network $NET --env-file \$R/shared/.env vipphone-staging:\$(readlink \$R/current | xargs basename) python scripts/cleanup_test_data.py $1"
}
step 09-don-dem  cleanup ""
step 09-don-xoa  cleanup "--apply"
step 09-sau-cung rsh "docker exec $PG psql -U vipphone -d $DB -Atc \"select 'head='||(select version_num from alembic_version)||' bang='||(select count(*) from information_schema.tables where table_schema=current_schema() and table_type='BASE TABLE')\"; readlink $ROOT_R/current; docker ps --format '{{.Names}} {{.Image}} {{.Status}} {{.Ports}}' | grep vipphone-staging; echo 'KẾT QUẢ: trạng thái cuối'"

echo "TẤT CẢ BƯỚC ĐÃ CHẠY" >> "$SUMMARY"
finish 0
