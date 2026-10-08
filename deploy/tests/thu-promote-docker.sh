#!/usr/bin/env bash
# =============================================================================
# BÀI THỬ DOCKER THẬT cho docker_promote (#86).  Chạy:  bash deploy/tests/thu-promote-docker.sh
# =============================================================================
# thu-deploy.sh không chạy Docker nên đã không thấy lỗi: bản cũ không bị dừng,
# vẫn giữ cổng, và mọi lượt deploy chết ở bước "đổi sang bản mới". Bài này dựng
# đúng hình dạng staging đo ngày 2026-10-08 (container cũ giữ 0.0.0.0:<cổng>)
# rồi gọi docker_promote THẬT, với remote_sh chạy tại máy thay cho SSH.
#
# Dùng ảnh postgres:16 làm "ứng dụng" (chỉ cần một tiến trình chạy lâu).
# Không có Docker / không có ảnh ⇒ BỎ QUA (mã 0), in rõ là chưa thử.
# Chỉ đụng container/mạng mang tiền tố vipphone-promotetest-.
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$(dirname "$HERE")")"
C=vipphone-promotetest-app
NET=vipphone-promotetest-net
PORT="${PROMOTE_TEST_PORT:-28080}"
IMG_BASE=postgres:16

PASS=0; FAIL=0
ok()  { printf '  \033[32mPASS\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }

if ! docker info >/dev/null 2>&1 || ! docker image inspect "$IMG_BASE" >/dev/null 2>&1; then
  echo "BỎ QUA: không có Docker hoặc ảnh $IMG_BASE — docker_promote CHƯA được thử."
  exit 0
fi

ROOT="$(mktemp -d)"
cleanup() {
  docker ps -aq --filter "name=^$C" | xargs -r docker rm -f >/dev/null 2>&1
  docker network rm "$NET" >/dev/null 2>&1
  docker image rm vipphone-staging:20261008-000000-aaaaaaa vipphone-staging:20261008-000001-bbbbbbb >/dev/null 2>&1
  rm -rf "$ROOT"
}
trap cleanup EXIT
cleanup; ROOT="$(mktemp -d)"

docker network create "$NET" >/dev/null
docker tag "$IMG_BASE" vipphone-staging:20261008-000000-aaaaaaa
docker tag "$IMG_BASE" vipphone-staging:20261008-000001-bbbbbbb
mkdir -p "$ROOT/staging/shared" "$ROOT/staging/releases/20261008-000000-aaaaaaa" \
         "$ROOT/staging/releases/20261008-000001-bbbbbbb"
echo POSTGRES_HOST_AUTH_METHOD=trust > "$ROOT/staging/shared/.env"

# Một lượt promote: dựng container tạm như docker_run_release, rồi promote thật.
promote() {
  local rel="$1" img_override="${2:-}"
  docker run -d --name "$C-new" -e POSTGRES_HOST_AUTH_METHOD=trust "$IMG_BASE" >/dev/null
  bash -c "
    . '$REPO/deploy/common.sh'; load_conf; select_env staging
    ENV_ROOT='$ROOT/staging'; ENV_USER=thu; ENV_HOST=tai-may
    remote_sh() { ${img_override:+sed 's#vipphone-staging:$rel#vipphone-staging:khong-ton-tai#' |} bash -seuo pipefail; }
    git_sha() { echo ${rel##*-}; }
    docker_promote '$rel' '$PORT' '$C' '$NET'
  " >/dev/null 2>&1
}
running() { docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null; }
image_of() { docker inspect -f '{{.Config.Image}}' "$1" 2>/dev/null; }
n_running_prev() { docker ps -q --filter "name=^$C-prev-" | wc -l | tr -d ' '; }

echo "== Bản cũ kiểu G14 giữ 0.0.0.0:$PORT (đúng hình dạng staging đo được)"
docker run -d --name "$C" -p "0.0.0.0:$PORT:8000" -e POSTGRES_HOST_AUTH_METHOD=trust \
  --restart unless-stopped "$IMG_BASE" >/dev/null

echo "== 1. Promote lần đầu"
promote 20261008-000000-aaaaaaa; code=$?
[ "$code" = 0 ] && ok "docker_promote thoát 0" || bad "docker_promote thoát $code"
[ "$(running "$C")" = true ] && ok "$C đang chạy" || bad "$C KHÔNG chạy"
[ "$(image_of "$C")" = vipphone-staging:20261008-000000-aaaaaaa ] && ok "đúng ảnh bản mới" || bad "sai ảnh: $(image_of "$C")"
[ "$(n_running_prev)" = 0 ] && ok "bản cũ đã DỪNG (không còn giữ cổng)" || bad "$(n_running_prev) bản cũ vẫn chạy"
[ "$(readlink "$ROOT/staging/current" | xargs -r basename)" = 20261008-000000-aaaaaaa ] && ok "current → bản mới" || bad "current sai"

echo "== 2. Promote lần hai (lượt deploy thường)"
sleep 1  # tên bản trước có hậu tố giây
promote 20261008-000001-bbbbbbb; code=$?
[ "$code" = 0 ] && ok "docker_promote thoát 0" || bad "docker_promote thoát $code"
[ "$(image_of "$C")" = vipphone-staging:20261008-000001-bbbbbbb ] && ok "đúng ảnh bản mới" || bad "sai ảnh: $(image_of "$C")"
[ "$(n_running_prev)" = 0 ] && ok "mọi bản trước đã dừng" || bad "$(n_running_prev) bản trước vẫn chạy"
[ "$(readlink "$ROOT/staging/previous" | xargs -r basename)" = 20261008-000000-aaaaaaa ] && ok "previous → bản trước (rollback có chỗ về)" || bad "previous sai"

echo "== 3. Bản mới KHÔNG chạy được ⇒ phải dựng lại bản trước, thoát ≠ 0"
sleep 1
promote 20261008-000000-aaaaaaa hong; code=$?
[ "$code" != 0 ] && ok "docker_promote thoát $code (≠ 0)" || bad "docker_promote báo thành công dù bản mới không chạy"
[ "$(running "$C")" = true ] && ok "$C vẫn đang chạy (môi trường không bị bỏ trống)" || bad "KHÔNG còn bản nào chạy"
[ "$(image_of "$C")" = vipphone-staging:20261008-000001-bbbbbbb ] && ok "đó là bản trước" || bad "sai ảnh: $(image_of "$C")"

printf '\n=== %d đạt · %d không đạt\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ]
