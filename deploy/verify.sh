#!/usr/bin/env bash
# =============================================================================
# NGHIỆM THU SAU TRIỂN KHAI — VIP PHONE
#   ./deploy/verify.sh staging
#   ./deploy/verify.sh production
# =============================================================================
# Đây là thứ DUY NHẤT được sinh ra phiếu cho phép production chạy
# (deploy/state/staging-pass/<release_id>.json).
#
# ⚠️  LUẬT §12.1 CỦA VAULT, viết lại cho script này:
#     *thứ dùng để kiểm chứng phải độc lập với thứ được kiểm chứng.*
#     Vì vậy:
#       · KHÔNG tin release.json để biết mã nào đang chạy — nó do lượt triển
#         khai tự viết. Mã đang chạy được đo bằng băm nội dung file TRÊN MÁY
#         CHỦ và so với băm của cây đã commit, bằng CÙNG MỘT phép đo.
#       · KHÔNG coi "container đang tồn tại" là "ứng dụng chạy được".
#       · Mỗi mục in rõ nó đo được gì, và phần nào nó KHÔNG đo.
# =============================================================================
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
load_conf
select_env "${1:-}"
require_host

case "$ENV_NAME" in
  staging)    PORT="$STAGING_PORT";    CONTAINER="$PROJECT-staging-app";  PG_CONTAINER="$STAGING_PG_CONTAINER";    PG_DB="$STAGING_PG_DB";    PG_USER="$STAGING_PG_USER" ;;
  production) PORT="$PRODUCTION_PORT"; CONTAINER="$PROJECT-prod-app";     PG_CONTAINER="$PRODUCTION_PG_CONTAINER"; PG_DB="$PRODUCTION_PG_DB"; PG_USER="$PRODUCTION_PG_USER" ;;
esac

PASS=0; FAIL=0
p() { ok "$1"; PASS=$((PASS + 1)); }
f() { bad "$1"; FAIL=$((FAIL + 1)); }

step "NGHIỆM THU $ENV_NAME — $(_ts)"

# --- 0. Bản nào đang chạy -------------------------------------------------
CUR_REL="$(remote_capture <<REMOTE
readlink "$ENV_ROOT/current" 2>/dev/null | xargs -r basename || true
REMOTE
)"
[ -n "$CUR_REL" ] || die "không đọc được liên kết current trên $ENV_NAME — chưa có bản nào triển khai?"
log "bản đang trỏ bởi current: $CUR_REL"

# --- 1. Container đang chạy (và KHÔNG khởi động lại liên tục) ------------
out="$(remote_capture <<REMOTE
docker inspect -f '{{.State.Status}} {{.RestartCount}} {{.State.StartedAt}}' "$CONTAINER" 2>/dev/null || echo "khong-co 0 -"
REMOTE
)"
set -- $out
case "$1" in
  running)
    p "container $CONTAINER đang chạy (khởi động lại $2 lần, từ $3)"
    # RestartCount cao nghĩa là nó đang chết rồi được dựng lại — "running" khi
    # đó vẫn đúng mà vô nghĩa. Đây là ca STG-1 đã xảy ra thật (RestartCount=4).
    if [ "${2:-0}" -gt 0 ]; then
      f "RestartCount=$2 — container ĐANG chết rồi tự dựng lại, không phải ổn định"
    fi
    ;;
  *) f "container $CONTAINER không chạy (trạng thái: $1)" ;;
esac

# --- 2. Health (liveness) ------------------------------------------------
out="$(remote_capture <<REMOTE
curl -s -o /dev/null -w '%{http_code}' -m 10 "http://127.0.0.1:$PORT$HEALTH_PATH" || echo 000
REMOTE
)"
[ "$out" = "200" ] && p "$HEALTH_PATH → 200" || f "$HEALTH_PATH → $out"

# --- 3. Readiness (có chạm database) -------------------------------------
out="$(remote_capture <<REMOTE
curl -s -m 10 "http://127.0.0.1:$PORT$READY_PATH" || echo '{}'
REMOTE
)"
case "$out" in
  *'"status":"ready"'*|*'"status": "ready"'*) p "$READY_PATH → ready" ;;
  *) f "$READY_PATH chưa ready: $(printf '%s' "$out" | head -c 200)" ;;
esac

# --- 4. Database nối được, và migration ở head ---------------------------
out="$(remote_capture <<REMOTE
docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc \
  "select coalesce((select version_num from alembic_version limit 1),'KHONG-CO')" 2>/dev/null || echo "LOI-PSQL"
REMOTE
)"
case "$out" in
  LOI-PSQL|"") f "không truy vấn được database $PG_DB" ;;
  KHONG-CO)    f "database chưa có bảng alembic_version — chưa migration" ;;
  *)
    HEAD_DB="$out"
    heads="$(remote_capture <<REMOTE
docker run --rm --network "\$(docker inspect -f '{{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}}{{end}}' "$CONTAINER")" \
  --env-file "$ENV_ROOT/shared/.env" "$PROJECT-$ENV_NAME:$CUR_REL" alembic heads 2>/dev/null \
  | grep -oE '^[0-9a-z_]+' | head -1 || true
REMOTE
)"
    if [ -n "$heads" ] && [ "$heads" = "$HEAD_DB" ]; then
      p "migration ở head: $HEAD_DB (khớp alembic heads của bản đang chạy)"
    elif [ -n "$heads" ]; then
      f "migration LỆCH: database $HEAD_DB ≠ heads của mã $heads"
    else
      # Nói rõ là chưa đo được, KHÔNG nói là đạt.
      f "đọc được database head ($HEAD_DB) nhưng KHÔNG đọc được alembic heads của mã ⇒ chưa kết luận được"
    fi
    ;;
esac

# --- 5. Trang chính, API, file tĩnh --------------------------------------
for path in "/" "/api/config" "/assets/css/main.css"; do
  out="$(remote_capture <<REMOTE
curl -s -o /dev/null -w '%{http_code}' -m 10 "http://127.0.0.1:$PORT$path" || echo 000
REMOTE
)"
  case "$out" in
    200) p "GET $path → 200" ;;
    404) f "GET $path → 404" ;;
    *)   f "GET $path → $out" ;;
  esac
done

# --- 6. Smoke test KHÔNG PHÁ DỮ LIỆU -------------------------------------
# Cố ý gửi payload SAI: nó chứng minh tầng kiểm tra dữ liệu đang sống mà không
# tạo ra lead thật nào. Đây là lý do smoke test này chạy được cả trên production.
out="$(remote_capture <<REMOTE
curl -s -o /dev/null -w '%{http_code}' -m 10 -X POST \
  -H 'Content-Type: application/json' \
  -d '{"phone":"KHONG-PHAI-SO"}' \
  "http://127.0.0.1:$PORT/api/leads" || echo 000
REMOTE
)"
case "$out" in
  422|400) p "POST /api/leads với dữ liệu sai → $out (tầng kiểm tra dữ liệu còn sống, KHÔNG tạo lead)" ;;
  200|201) f "POST /api/leads với dữ liệu SAI lại trả $out — kiểm tra dữ liệu KHÔNG chạy" ;;
  *)       f "POST /api/leads → $out" ;;
esac

# --- 7. Log không có lỗi mới --------------------------------------------
out="$(remote_capture <<REMOTE
docker logs --since 10m "$CONTAINER" 2>&1 | grep -cE 'Traceback|CRITICAL|ERROR|RuntimeError' || true
REMOTE
)"
# `grep -c` trả mã 1 khi đếm 0 — đã chặn bằng `|| true`, nếu không thì cả hàm
# này thoát sớm và mục bị bỏ qua trong im lặng.
if [ "${out:-0}" = "0" ]; then
  p "log 10 phút gần đây: 0 dòng Traceback/ERROR/CRITICAL"
else
  f "log 10 phút gần đây có $out dòng lỗi — xem: docker logs --since 10m $CONTAINER"
fi

# --- 8. Secret không lọt vào log ----------------------------------------
out="$(remote_capture <<REMOTE
docker logs --since 60m "$CONTAINER" 2>&1 | grep -cE 'DATABASE_URL|postgresql(\+psycopg)?://[^ ]*:[^ @]*@|STAFF_API_KEYS|TURNSTILE_SECRET' || true
REMOTE
)"
[ "${out:-0}" = "0" ] && p "log 60 phút: 0 dòng chứa secret theo các mẫu đã dò" \
  || f "log có $out dòng khớp mẫu secret"

# --- 9. SHA/bản đang chạy — phép đo ĐỘC LẬP ------------------------------
# Băm nội dung các file của bản phát hành trên máy chủ, rồi so với băm của
# CHÍNH cây commit ở máy trạm, bằng cùng một công thức.
step "9. ĐỐI CHIẾU MÃ ĐANG CHẠY VỚI GIT"
SHA_LOCAL="$(git_sha)"
rsha="$(remote_tree_sha "$CUR_REL")"
tmp="$(mktemp -d)"
git -C "$REPO_ROOT" archive --format=tar "$SHA_LOCAL" | tar -x -C "$tmp"
lsha="$( cd "$tmp" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 \
          | awk '{print $1"  "$2}' | shasum -a 256 | awk '{print $1}' )"
rm -rf "$tmp"
log "băm máy chủ : ${rsha:-(không đo được)}"
log "băm máy trạm: ${lsha:-(không đo được)}"
if [ -z "$rsha" ]; then
  f "KHÔNG đo được băm trên máy chủ ⇒ không kết luận mã đang chạy khớp Git"
elif [ "$rsha" = "$lsha" ]; then
  p "mã trên máy chủ KHỚP BYTE với cây commit $SHA_LOCAL"
else
  f "mã trên máy chủ KHÁC cây commit $SHA_LOCAL — đừng tin release.json, nó do chính lượt deploy viết"
fi

# --- 10. Phạm vi KHÔNG đo được: nói ra, không bỏ qua ---------------------
step "PHẠM VI CỦA PHIẾU NÀY"
cat <<'SCOPE'
  Phiếu này đo: container, health, readiness, database + migration head,
  3 đường HTTP, một smoke test không phá dữ liệu, log lỗi, log secret,
  và băm mã trên máy chủ so với cây commit.

  Phiếu này KHÔNG đo:
    · TLS/HTTPS từ Internet — đo ở 127.0.0.1 trên máy chủ, nên nó không nói gì
      về reverse proxy, chứng chỉ, hay DNS.
    · Hành vi dưới tải.
    · Trình duyệt thật (E2E) — việc của `make test-e2e`.
    · Dữ liệu khách thật đúng/sai về nghiệp vụ.
SCOPE

# --- Kết quả và phiếu ----------------------------------------------------
step "KẾT QUẢ: $PASS đạt · $FAIL không đạt"
if [ "$FAIL" -ne 0 ]; then
  if [ "$ENV_NAME" = staging ]; then
    rm -f "$(gate_file "$CUR_REL")"
    log "đã KHÔNG sinh phiếu (và xoá phiếu cũ của $CUR_REL nếu có)"
  fi
  die "nghiệm thu $ENV_NAME KHÔNG ĐẠT — $FAIL mục hỏng. Production vẫn bị chặn."
fi

if [ "$ENV_NAME" = staging ]; then
  mkdir -p "$STATE_DIR/staging-pass"
  G="$(gate_file "$CUR_REL")"
  cat > "$G" <<JSON
{
  "project": "$PROJECT",
  "release_id": "$CUR_REL",
  "git_sha": "$SHA_LOCAL",
  "verified_at": "$(_ts)",
  "staging_host_tree_sha256": "$rsha",
  "local_tree_sha256": "$lsha",
  "checks_passed": $PASS,
  "checks_failed": 0,
  "verified_by": "deploy/verify.sh"
}
JSON
  ok "đã sinh phiếu staging PASS: $G"
  printf '\n  BƯỚC TIẾP THEO: Owner nghiệm thu, rồi ./deploy/production.sh\n'
else
  ok "production nghiệm thu ĐẠT cho bản $CUR_REL"
fi
