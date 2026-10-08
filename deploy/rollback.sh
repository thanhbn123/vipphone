#!/usr/bin/env bash
# =============================================================================
# ROLLBACK — VIP PHONE
#   ./deploy/rollback.sh staging
#   ./deploy/rollback.sh production
#   ./deploy/rollback.sh production --yes      (không hỏi lại; dùng khi gọi tự động)
# =============================================================================
# Rollback ở đây là: trỏ `current` về bản TRƯỚC, chạy lại ảnh của bản đó, rồi
# health check và xác nhận bản/SHA.
#
# ⚠️  ROLLBACK NÀY CHỈ QUAY LẠI **MÃ**, KHÔNG quay lại **LƯỢC ĐỒ DATABASE**.
#     Cố ý. Một `alembic downgrade` chỉ an toàn khi chính migration đó được viết
#     để đảo ngược được — mà không thể suy ra điều đó từ việc hàm downgrade() có
#     tồn tại. Hạ cấp sai thì MẤT DỮ LIỆU, và không rollback nào vá lại được.
#     Vì vậy luật là: migration phải tương thích ngược, để mã cũ chạy được trên
#     lược đồ mới. Xem docs/DIRECT-DEPLOY.md §6.
# =============================================================================
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
load_conf
select_env "${1:-}"
require_host
AUTO="${2:-}"

case "$ENV_NAME" in
  staging)    PORT="$STAGING_PORT";    CONTAINER="$PROJECT-staging-app"; NETWORK="$STAGING_NETWORK" ;;
  production) PORT="$PRODUCTION_PORT"; CONTAINER="$PROJECT-prod-app";    NETWORK="$PRODUCTION_NETWORK" ;;
esac

step "ROLLBACK $ENV_NAME"

CUR="$(remote_capture <<REMOTE
readlink "$ENV_ROOT/current" 2>/dev/null | xargs -r basename || true
REMOTE
)"
TARGET="$(remote_capture <<REMOTE
readlink "$ENV_ROOT/previous" 2>/dev/null | xargs -r basename || true
REMOTE
)"
[ -n "$TARGET" ] || die "không có bản trước để quay về ($ENV_ROOT/previous trống).
     Không bịa ra một bản nào khác: chọn sai bản để rollback còn tệ hơn không rollback."
[ "$TARGET" != "$CUR" ] || die "previous trùng current ($CUR) — không có gì để quay về"

printf '  đang chạy : %s\n' "${CUR:-(không rõ)}"
printf '  quay về   : %s\n' "$TARGET"

MIG="$(remote_capture <<REMOTE
ls -1 "$ENV_ROOT/releases/$CUR/migrations/versions" 2>/dev/null | wc -l
REMOTE
)"
MIG_T="$(remote_capture <<REMOTE
ls -1 "$ENV_ROOT/releases/$TARGET/migrations/versions" 2>/dev/null | wc -l
REMOTE
)"
if [ "${MIG:-0}" -gt "${MIG_T:-0}" ] 2>/dev/null; then
  warn "bản đang chạy có ${MIG} migration, bản đích có ${MIG_T}"
  warn "LƯỢC ĐỒ SẼ KHÔNG ĐƯỢC HẠ CẤP. Mã cũ phải chạy được trên lược đồ mới."
  warn "Nếu nó không chạy được, rollback này sẽ hỏng — và health check dưới đây sẽ nói ra."
fi

if [ "$AUTO" != "--yes" ] && [ "$ENV_NAME" = production ]; then
  printf '\n  Gõ đúng chữ %sROLLBACK%s để tiếp tục: ' "$C_WARN" "$C_0"
  read -r answer
  [ "$answer" = "ROLLBACK" ] || die "đã huỷ — không đổi gì"
fi

step "CHẠY LẠI BẢN $TARGET"
remote_sh <<REMOTE
ROOT="$ENV_ROOT"
IMG="$PROJECT-$ENV_NAME:$TARGET"
docker image inspect "\$IMG" >/dev/null 2>&1 || {
  echo "ảnh \$IMG không còn — build lại từ mã của bản đó" >&2
  docker build -q -t "\$IMG" -f "\$ROOT/releases/$TARGET/deploy/Dockerfile" "\$ROOT/releases/$TARGET" >/dev/null
}
SHA_T="\$(sed -n 's/.*"git_sha"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "\$ROOT/releases/$TARGET/release.json" 2>/dev/null | head -1)"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" \
  --network "$NETWORK" --env-file "\$ROOT/shared/.env" \
  -e RELEASE_ID="$TARGET" -e GIT_SHA="\$SHA_T" \
  -p "127.0.0.1:$PORT:8000" -v "$PROJECT-$ENV_NAME-media:/app/var/media" \
  --restart unless-stopped "\$IMG" >/dev/null

# current ↔ previous đổi chỗ, để rollback hai lần quay lại chỗ cũ chứ không
# đi tiếp xuống một bản thứ ba nào không ai chọn.
OLDCUR="$CUR"
ln -sfn "\$ROOT/releases/$TARGET" "\$ROOT/current.tmp" && mv -f "\$ROOT/current.tmp" "\$ROOT/current"
[ -n "\$OLDCUR" ] && { ln -sfn "\$ROOT/releases/\$OLDCUR" "\$ROOT/previous.tmp" && mv -f "\$ROOT/previous.tmp" "\$ROOT/previous"; }
printf '%s\t%s\tROLLBACK→%s\t%s\n' "\$(date -Is)" "$ENV_NAME" "$TARGET" "\$SHA_T" >> "\$ROOT/history.log"
echo "đã chạy lại $TARGET"
REMOTE

step "HEALTH SAU ROLLBACK"
if [ "${DEPLOY_DRY_RUN:-0}" = "1" ]; then
  warn "chạy khô: không gọi health"
else
  res="$(remote_capture <<REMOTE
for i in \$(seq 1 30); do
  code=\$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://127.0.0.1:$PORT$HEALTH_PATH" || echo 000)
  [ "\$code" = "200" ] && { echo "OK"; exit 0; }
  sleep 2
done
echo "FAIL \$code"; exit 1
REMOTE
)" || die "ROLLBACK KHÔNG KHOẺ: health không lên 200 sau 60 giây.
     $ENV_NAME đang ở trạng thái xấu và cần người xử ngay. KHÔNG tự thử bản thứ ba."
  ok "health 200 sau rollback"
fi

step "XÁC NHẬN BẢN/SHA ĐANG CHẠY"
# Ba phép đo rời nhau, mỗi phép một lệnh, để một lệnh hỏng không làm hai lệnh
# kia bị bỏ qua trong im lặng.
NOW_REL="$(remote_capture <<REMOTE
readlink "$ENV_ROOT/current" 2>/dev/null | xargs -r basename || true
REMOTE
)"
NOW_SHA="$(remote_capture <<REMOTE
grep -o '"git_sha"[^,]*' "$ENV_ROOT/current/release.json" 2>/dev/null | head -1 | cut -d'"' -f4 || true
REMOTE
)"
NOW_CT="$(remote_capture <<REMOTE
docker inspect -f '{{.State.Status}} restart={{.RestartCount}}' "$CONTAINER" 2>/dev/null || echo khong-doc-duoc
REMOTE
)"
printf '  current   : %s\n' "${NOW_REL:-(không đo được)}"
printf '  git_sha   : %s\n' "${NOW_SHA:-(không đo được)}"
printf '  container : %s\n' "${NOW_CT:-(không đo được)}"
if [ "${DEPLOY_DRY_RUN:-0}" != "1" ] && [ "$NOW_REL" != "$TARGET" ]; then
  die "current đang là '${NOW_REL:-rỗng}' chứ không phải '$TARGET' — rollback CHƯA xong"
fi
ok "rollback $ENV_NAME về $TARGET xong"
printf '\n  Nhớ: lược đồ database KHÔNG bị hạ cấp. Nếu bản cũ không chạy được với\n'
printf '  lược đồ mới thì phải vá tiến lên, không vá lùi.\n'
