#!/usr/bin/env bash
# =============================================================================
# THƯ VIỆN CHUNG cho bộ triển khai trực tiếp (direct deploy) — VIP PHONE
# =============================================================================
# Mô hình: LOCAL CODE → LOCAL TEST → VPS STAGING → STAGING VERIFY →
#          OWNER ACCEPTANCE → VPS PRODUCTION → PRODUCTION VERIFY → SYNC GITHUB
#
# GitHub KHÔNG còn là cửa quyết định triển khai. Nhưng Git, SHA, test, sao lưu,
# staging, rollback và nghiệm thu sau triển khai thì KHÔNG bỏ cái nào.
#
# File này chỉ định nghĩa hàm và nạp cấu hình. Nó KHÔNG tự làm gì khi được nạp.
#
# ⚠️  BA ĐIỀU FILE NÀY CỐ Ý KHÔNG LÀM:
#   1. Không bao giờ in giá trị secret. Chỉ in TÊN biến và trạng thái có/không.
#   2. Không bao giờ chép secret từ máy trạm lên máy chủ. Secret nằm ở
#      <APP_ROOT>/shared/.env trên máy chủ, do người đặt một lần.
#   3. Không tự hạ cấp (downgrade) database. Xem `migration_guard()`.
# =============================================================================

set -Eeuo pipefail

# --- Vị trí ---------------------------------------------------------------
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$DEPLOY_DIR/.." && pwd)"
STATE_DIR="$DEPLOY_DIR/state"

# --- Màu và ghi log -------------------------------------------------------
# Tắt màu khi không phải terminal, để log file không lẫn mã escape.
if [ -t 1 ]; then
  C_OK=$'\033[32m'; C_BAD=$'\033[31m'; C_WARN=$'\033[33m'; C_DIM=$'\033[2m'; C_0=$'\033[0m'
else
  C_OK=''; C_BAD=''; C_WARN=''; C_DIM=''; C_0=''
fi

_ts() { date "+%Y-%m-%d %H:%M:%S %z"; }

log()   { printf '%s %s\n' "$(_ts)" "$*"; }
step()  { printf '\n%s=== %s ===%s\n' "$C_DIM" "$*" "$C_0"; }
ok()    { printf '  %sPASS%s  %s\n' "$C_OK" "$C_0" "$*"; }
bad()   { printf '  %sFAIL%s  %s\n' "$C_BAD" "$C_0" "$*"; }
warn()  { printf '  %sWARN%s  %s\n' "$C_WARN" "$C_0" "$*"; }

# die: dừng hẳn với mã thoát khác 0. Dùng cho mọi cửa khoá (fail closed).
die() { printf '\n%sDỪNG:%s %s\n' "$C_BAD" "$C_0" "$*" >&2; exit 1; }

# Bẫy lỗi: `set -E` + ERR trap để một lệnh hỏng ở giữa không bị trôi qua im lặng
# (§12.2 của CLAUDE.md: cấm nuốt lỗi).
_on_err() {
  local code=$? line=${BASH_LINENO[0]:-?} cmd=${BASH_COMMAND:-?}
  printf '\n%sLỖI%s mã %d tại dòng %s: %s\n' "$C_BAD" "$C_0" "$code" "$line" "$cmd" >&2
  exit "$code"
}
trap _on_err ERR

# --- Nạp cấu hình ---------------------------------------------------------
# deploy/deploy.conf là cấu hình KHÔNG secret, có trong Git.
# deploy/deploy.local.conf (nếu có) ghi đè, KHÔNG vào Git — dùng cho đường dẫn
# khoá SSH riêng của từng máy trạm.
load_conf() {
  [ -f "$DEPLOY_DIR/deploy.conf" ] || die "thiếu deploy/deploy.conf"
  # shellcheck disable=SC1091
  . "$DEPLOY_DIR/deploy.conf"
  if [ -f "$DEPLOY_DIR/deploy.local.conf" ]; then
    # shellcheck disable=SC1091
    . "$DEPLOY_DIR/deploy.local.conf"
  fi
  : "${PROJECT:?deploy.conf thiếu PROJECT}"
  : "${APP_ROOT:?deploy.conf thiếu APP_ROOT}"
  : "${KEEP_RELEASES:=5}"
  : "${HEALTH_PATH:=/api/health}"
  : "${READY_PATH:=/api/ready}"
}

# --- Môi trường: staging | production ------------------------------------
# Đặt các biến ENV_* theo môi trường được chọn. Fail closed: môi trường lạ thì dừng.
select_env() {
  local env="${1:-}"
  case "$env" in
    staging)
      ENV_NAME=staging
      ENV_UPPER=STAGING   # không dùng ${ENV_NAME^^}: bash 3.2 mặc định của macOS không có
      ENV_HOST="${STAGING_HOST:-}"
      ENV_USER="${STAGING_USER:-}"
      ENV_KEY="${STAGING_SSH_KEY:-}"
      ENV_URL="${STAGING_URL:-}"
      ENV_TEMP_PORT="${STAGING_TEMP_PORT:-}"
      ENV_ROOT="${APP_ROOT}/staging"
      ENV_RUNTIME="${STAGING_RUNTIME:-docker}"
      ;;
    production)
      ENV_NAME=production
      ENV_UPPER=PRODUCTION
      ENV_HOST="${PRODUCTION_HOST:-}"
      ENV_USER="${PRODUCTION_USER:-}"
      ENV_KEY="${PRODUCTION_SSH_KEY:-}"
      ENV_URL="${PRODUCTION_URL:-}"
      ENV_TEMP_PORT="${PRODUCTION_TEMP_PORT:-}"
      ENV_ROOT="${APP_ROOT}/production"
      ENV_RUNTIME="${PRODUCTION_RUNTIME:-docker}"
      ;;
    *) die "môi trường phải là 'staging' hoặc 'production', nhận được: '${env:-(rỗng)}'" ;;
  esac
}

# require_host: dừng nếu môi trường chưa có host/khoá. Đây là cửa khoá quan
# trọng nhất của cả bộ: KHÔNG cho phép "chạy một nửa rồi báo thành công".
require_host() {
  [ -n "${ENV_HOST:-}" ] || die "$ENV_NAME: chưa có host. Điền ${ENV_UPPER}_HOST trong deploy/deploy.local.conf"
  [ -n "${ENV_USER:-}" ] || die "$ENV_NAME: chưa có user. Điền ${ENV_UPPER}_USER"
  [ -n "${ENV_KEY:-}"  ] || die "$ENV_NAME: chưa có khoá SSH. Điền ${ENV_UPPER}_SSH_KEY"
  # Chốt SAI HOST: staging tuyệt đối không được trỏ vào host production (và
  # ngược lại). Đặt nhầm một IP trong deploy.local.conf là đủ để "deploy staging"
  # chạy migration + thay container trên máy production.
  if [ "$ENV_NAME" = staging ]; then
    local h
    for h in ${KNOWN_PRODUCTION_HOSTS:-} ${PRODUCTION_HOST:-}; do
      [ "$ENV_HOST" = "$h" ] && die "SAI HOST: STAGING_HOST=$ENV_HOST là host PRODUCTION — dừng."
    done
  else
    [ -n "${STAGING_HOST:-}" ] && [ "$ENV_HOST" = "$STAGING_HOST" ] \
      && die "SAI HOST: PRODUCTION_HOST=$ENV_HOST trùng STAGING_HOST — dừng."
  fi
  # Nở rộng ~ một cách tường minh: `[ -f "~/..." ]` luôn sai.
  ENV_KEY="${ENV_KEY/#\~/$HOME}"
  [ -f "$ENV_KEY" ] || die "$ENV_NAME: không thấy file khoá SSH tại $ENV_KEY"
}

# --- SSH ------------------------------------------------------------------
# MỌI lệnh trên máy chủ đi qua đúng một hàm này, nên chỉ có một chỗ phải sửa khi
# đổi cách kết nối, và chỉ có một chỗ phải đọc khi muốn biết script làm gì ở xa.
#
# `-n` KHÔNG được dùng ở đây: remote_sh nhận script qua stdin (`bash -s`). Thay
# vào đó các vòng lặp gọi remote_sh phải tự đóng stdin của mình — xem
# ssh-trong-script-nuot-stdin trong ghi nhớ.
remote_sh() {
  local script
  script="$(cat)"
  if [ "${DEPLOY_DRY_RUN:-0}" = "1" ]; then
    printf '  %s[CHẠY KHÔ] ssh %s@%s bash -s <<<%s dòng%s\n' \
      "$C_DIM" "$ENV_USER" "$ENV_HOST" "$(printf '%s' "$script" | wc -l | tr -d ' ')" "$C_0"
    return 0
  fi
  printf '%s' "$script" | ssh \
    -o BatchMode=yes -o ConnectTimeout="${SSH_CONNECT_TIMEOUT:-10}" \
    -o StrictHostKeyChecking=accept-new \
    -i "$ENV_KEY" "$ENV_USER@$ENV_HOST" 'bash -seuo pipefail'
}

# remote_capture: như remote_sh nhưng trả stdout để so sánh. Ở chế độ chạy khô
# nó trả chuỗi rỗng — và mọi chỗ gọi nó PHẢI coi chuỗi rỗng là "chưa đo được",
# không bao giờ coi là "khớp".
remote_capture() { remote_sh; }

# done_or_dry: in PASS khi làm thật, in "CHƯA LÀM" khi chạy khô.
#
# Vì sao cần hàm riêng: lượt chạy khô đầu tiên in ra
# "PASS đã đưa bản lên máy chủ và kiểm mã băm hai đầu" trong khi nó KHÔNG hề
# nối tới máy chủ nào. Đó đúng là dạng lỗi §12.1 của CLAUDE.md — thứ dùng để
# báo kết quả lại tự nó không trung thực. Một dòng PASS sai còn tệ hơn không có
# dòng nào, vì nó được tin.
done_or_dry() {
  if [ "${DEPLOY_DRY_RUN:-0}" = "1" ]; then
    printf '  %sCHƯA LÀM%s  %s %s(chạy khô — không chạm máy chủ)%s\n' \
      "$C_WARN" "$C_0" "$1" "$C_DIM" "$C_0"
  else
    ok "$1"
  fi
}

# --- Nhận dạng bản phát hành ---------------------------------------------
# Dạng: YYYYMMDD-HHMMSS-<short_sha>, ví dụ 20261007-182500-a31df21
make_release_id() {
  local sha="$1"
  printf '%s-%s' "$(date +%Y%m%d-%H%M%S)" "${sha:0:7}"
}

RELEASE_ID_RE='^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}$'
valid_release_id() { [[ "$1" =~ $RELEASE_ID_RE ]]; }

# --- Cửa khoá Git ---------------------------------------------------------
git_sha()    { git -C "$REPO_ROOT" rev-parse HEAD; }
git_branch() { git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD; }

# Băm CÂY LÀM VIỆC đã commit — dùng để đối chiếu với máy chủ về sau.
# Đây là phép đo ĐỘC LẬP với release.json: release.json do chính lượt triển khai
# viết ra, nên nó không thể tự chứng minh rằng mã trên máy chủ đúng (§12.1).
git_tree_sha() { git -C "$REPO_ROOT" rev-parse 'HEAD^{tree}'; }

require_clean_worktree() {
  local dirty
  dirty="$(git -C "$REPO_ROOT" status --porcelain)"
  if [ -n "$dirty" ]; then
    printf '%s\n' "$dirty" | sed 's/^/    /'
    die "cây làm việc KHÔNG sạch. Triển khai mã chưa commit là triển khai mã không có SHA.
     Hãy commit hoặc stash. Script này KHÔNG tự xoá, không tự stash, không ghi đè gì của bạn."
  fi
}

# --- Sổ nghiệm thu staging (cửa vào production) --------------------------
# File này là ĐIỀU KIỆN BẮT BUỘC để production.sh chạy. Nó CHỈ được sinh ra bởi
# verify.sh sau khi đã đo thật trên staging — không script nào khác được ghi.
gate_file() { printf '%s/%s.json' "$STATE_DIR/staging-pass" "$1"; }

# --- Đọc một khoá đơn giản trong JSON ------------------------------------
# Cố ý KHÔNG dùng jq: máy trạm không chắc có jq, và thiếu jq mà im lặng bỏ qua
# phép kiểm thì đúng là hỏng im lặng. Chỉ đọc chuỗi phẳng, đủ cho release.json.
json_str() {
  local file="$1" key="$2"
  [ -f "$file" ] || return 1
  sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$file" | head -1
}

# --- HTTP -----------------------------------------------------------------
# url_host: tên máy trong URL — https://qua.viporder.vn/x → qua.viporder.vn
url_host() {
  local u="${1#*://}"
  u="${u%%/*}"; u="${u##*@}"
  printf '%s' "${u%%:*}"
}

# host_header: đối số curl cho mọi lần gọi ứng dụng qua 127.0.0.1 TRÊN MÁY CHỦ.
# Ứng dụng chạy TrustedHostMiddleware theo ALLOWED_HOSTS, nên gọi 127.0.0.1 trần
# bị trả "400 Invalid host header" (đo trên staging 2026-10-08) — health/verify
# sẽ luôn hỏng (#88). Dùng bên trong heredoc REMOTE: $(host_header).
host_header() {
  local h
  h="$(url_host "${ENV_URL:-}")"
  if [ -n "$h" ]; then printf "%s" "-H 'Host: $h'"; fi
  return 0
}

# require_ports: kiểm cổng TRƯỚC khi sao lưu/migration — hỏng ở đây thì chưa có gì
# bị đổi. Cổng tạm phải trống (hoặc do container tạm sót lại của chính dự án giữ);
# cổng chính phải trống hoặc do chính container của dự án giữ. Đo trên staging
# 2026-10-08: 18081 (= 18080 + 1, cổng tạm cũ) thuộc viporder-nginx-1 của dự án
# khác, và staging.sh chỉ phát hiện ra SAU khi đã migration (#88).
require_ports() {
  local port="$1" temp="$2" container="$3" out
  [ -n "$temp" ] || die "$ENV_NAME: chưa cấu hình cổng tạm (${ENV_UPPER}_TEMP_PORT trong deploy.conf)"
  [ "$temp" != "$port" ] || die "$ENV_NAME: cổng tạm trùng cổng chính ($port)"
  if [ "${DEPLOY_DRY_RUN:-0}" = "1" ]; then
    warn "chạy khô: không kiểm được cổng $port/$temp trên máy chủ"
    return 0
  fi
  # KHÔNG dùng `case` (hay bất kỳ dấu `)` lẻ nào) trong heredoc nằm trong `$( )`:
  # bash 3.2 của macOS đếm ngoặc cả trong thân heredoc, cắt `$(` tại `)` lẻ đầu
  # tiên ⇒ máy chủ nhận script cụt, phần còn lại chạy TẠI MÁY TRẠM (#92).
  # Bộ thử: deploy/tests/thu-deploy.sh mục "heredoc trong \$( )".
  out="$(remote_capture <<REMOTE
listening() { (exec 3<>"/dev/tcp/127.0.0.1/\$1") 2>/dev/null; }
owner() { docker ps --filter "publish=\$1" --format '{{.Names}}' | head -1; }
if listening $temp; then
  o="\$(owner $temp)"
  [ "\$o" = "$container-new" ] || { echo "TAM_BAN \${o:-tien-trinh-ngoai-docker}"; exit 0; }
fi
if listening $port; then
  o="\$(owner $port)"
  if [ "\$o" = "$container" ] || [ "\${o#$container-prev-}" != "\$o" ]; then echo "OK \$o"
  else echo "CHINH_BAN \${o:-tien-trinh-ngoai-docker}"
  fi
else
  echo "OK trong"
fi
REMOTE
)"
  case "$out" in
    OK\ *)       ok "cổng chính $port: ${out#OK } · cổng tạm $temp: trống" ;;
    TAM_BAN\ *)  die "cổng tạm $temp đang bị chiếm bởi '${out#TAM_BAN }'. Đổi ${ENV_UPPER}_TEMP_PORT — CHƯA có gì bị đổi." ;;
    CHINH_BAN\ *) die "cổng chính $port đang bị '${out#CHINH_BAN }' giữ, không phải $container — CHƯA có gì bị đổi." ;;
    *)            die "không kiểm được cổng trên máy chủ (nhận: '${out:-rỗng}') — CHƯA có gì bị đổi." ;;
  esac
}
# Trả về "<mã http> <thời gian giây>"; mã 000 nghĩa là không nối được.
http_probe() {
  local url="$1" timeout="${2:-15}"
  curl -sS -o /dev/null -m "$timeout" -w '%{http_code} %{time_total}' "$url" 2>/dev/null || printf '000 0'
}

# --- Cửa khoá migration ---------------------------------------------------
# KHÔNG tự hạ cấp database. Alembic có downgrade, nhưng một downgrade chỉ an
# toàn khi chính nó được viết để đảo ngược được — mà điều đó không thể suy ra
# từ việc hàm downgrade() có tồn tại.
migration_guard() {
  local direction="$1"
  case "$direction" in
    upgrade) return 0 ;;
    downgrade)
      die "TỪ CHỐI hạ cấp database tự động.
     Lược đồ không phải lúc nào cũng đảo ngược được, và một downgrade sai làm
     MẤT DỮ LIỆU — thứ không có rollback nào vá lại được.
     Cách đúng: migration tương thích ngược (backward-compatible), rồi rollback
     chỉ phần MÃ. Xem docs/DIRECT-DEPLOY.md §6."
      ;;
    *) die "migration_guard: hướng lạ '$direction'" ;;
  esac
}

# --- Tóm tắt cuối ---------------------------------------------------------
summary_line() { printf '\n%s %s\n' "$1" "$2"; }

export -f log step ok bad warn die 2>/dev/null || true

# =============================================================================
# PHẦN 2 — CƠ CHẾ PHÁT HÀNH (chạy bằng Docker, không cần sudo)
# =============================================================================
# Bố cục trên máy chủ:
#   <ENV_ROOT>/releases/<release_id>/   mã nguồn của một bản phát hành
#   <ENV_ROOT>/current                  liên kết mềm tới bản ĐANG CHẠY
#   <ENV_ROOT>/previous                 liên kết mềm tới bản TRƯỚC (để rollback)
#   <ENV_ROOT>/shared/.env              secret, do người đặt, KHÔNG do script
#   <ENV_ROOT>/backups/                 bản sao lưu CSDL
#   <ENV_ROOT>/history.log              sổ triển khai, chỉ ghi thêm
# =============================================================================

# build_artifact: đóng gói ĐÚNG cây đã commit. Dùng `git archive` nên thứ lên
# máy chủ không thể lẫn file chưa commit hay file rác trong thư mục làm việc.
build_artifact() {
  local release_id="$1" out_dir="$2"
  mkdir -p "$out_dir"
  ARTIFACT="$out_dir/$PROJECT-$release_id.tar.gz"
  git -C "$REPO_ROOT" archive --format=tar.gz -o "$ARTIFACT" HEAD
  ARTIFACT_SHA256="$(shasum -a 256 "$ARTIFACT" | awk '{print $1}')"
  ok "gói artifact: $(basename "$ARTIFACT") ($(wc -c <"$ARTIFACT" | tr -d ' ') byte)"
  ok "sha256 artifact: $ARTIFACT_SHA256"
}

# ship_release: đưa artifact lên và giải nén vào releases/<id>.
# KHÔNG đụng `current` — bản mới chỉ nằm chờ cho tới khi qua health check.
ship_release() {
  local release_id="$1"
  if [ "${DEPLOY_DRY_RUN:-0}" = "1" ]; then
    printf '  %s[CHẠY KHÔ] scp %s → %s@%s:%s/incoming/%s\n' "$C_DIM" \
      "$(basename "$ARTIFACT")" "$ENV_USER" "$ENV_HOST" "$ENV_ROOT" "$C_0"
  else
    remote_sh <<REMOTE
ROOT="$ENV_ROOT"
mkdir -p "\$ROOT/releases" "\$ROOT/shared" "\$ROOT/backups" "\$ROOT/incoming"
REMOTE
    scp -q -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$ENV_KEY" \
      "$ARTIFACT" "$ENV_USER@$ENV_HOST:$ENV_ROOT/incoming/" </dev/null
  fi

  remote_sh <<REMOTE
ROOT="$ENV_ROOT"
REL="\$ROOT/releases/$release_id"
ART="\$ROOT/incoming/$(basename "$ARTIFACT")"
[ -f "\$ART" ] || { echo "artifact không có trên máy chủ: \$ART" >&2; exit 1; }

# Kiểm mã băm TẠI MÁY CHỦ, trước khi giải nén. Nếu đường truyền làm hỏng gói
# thì phải biết ngay, không phải biết lúc ứng dụng không khởi động nổi.
GOT="\$(sha256sum "\$ART" | awk '{print \$1}')"
[ "\$GOT" = "$ARTIFACT_SHA256" ] || {
  echo "sha256 LỆCH: máy chủ \$GOT ≠ máy trạm $ARTIFACT_SHA256" >&2; exit 1; }

# Giải nén lại từ đầu nếu thư mục đã có (idempotent): cùng release_id phải cho
# cùng nội dung, không được là bản ghép của hai lượt.
rm -rf "\$REL"
mkdir -p "\$REL"
tar -xzf "\$ART" -C "\$REL"
rm -f "\$ART"
echo "đã giải nén: \$REL"
REMOTE
  done_or_dry "đã đưa bản $release_id lên máy chủ và kiểm mã băm hai đầu"
}

# require_shared_env: secret PHẢI có sẵn trên máy chủ. Không script nào tạo nó,
# không script nào in nó ra. Thiếu thì dừng — chạy với .env thiếu biến là cách
# chắc chắn nhất để hỏng im lặng sau khi đã báo thành công.
require_shared_env() {
  local out
  out="$(remote_capture <<REMOTE
ROOT="$ENV_ROOT"
if [ -f "\$ROOT/shared/.env" ]; then
  # Chỉ in SỐ biến và TÊN biến còn thiếu. Không bao giờ in giá trị.
  echo "CO \$(grep -cE '^[A-Z_]+=' "\$ROOT/shared/.env" || true)"
else
  echo "THIEU"
fi
REMOTE
)"
  if [ "${DEPLOY_DRY_RUN:-0}" = "1" ]; then
    warn "chạy khô: không kiểm được shared/.env"
    return 0
  fi
  case "$out" in
    CO\ *) ok "shared/.env có mặt (${out#CO } biến; giá trị KHÔNG được in ra)" ;;
    *) die "$ENV_NAME: thiếu $ENV_ROOT/shared/.env.
     Secret do người đặt một lần, trực tiếp trên máy chủ. Script không tạo hộ,
     và cố ý không chép secret từ máy trạm lên." ;;
  esac
}

# remote_tree_sha: băm nội dung thư mục bản phát hành TRÊN MÁY CHỦ, theo cùng
# một cách với `git archive` ở máy trạm, để đối chiếu được.
#
# ⚠️  PHẠM VI của phép đo này (§12.1 luật 3): nó chứng minh *các file theo dõi
# bởi Git* trên máy chủ khớp byte với cây đã commit. Nó KHÔNG chứng minh tiến
# trình đang chạy đúng các file đó — đó là việc của health check + ảnh container.
remote_tree_sha() {
  local release_id="$1"
  remote_capture <<REMOTE
cd "$ENV_ROOT/releases/$release_id" || exit 1
# Danh sách file sắp xếp ổn định, băm từng file rồi băm danh sách băm.
# release.json do chính lượt deploy ghi SAU lần băm đầu và không có trong Git —
# tính nó vào thì verify.sh luôn thấy "mã KHÁC cây commit" (#88).
find . -type f -not -path './.git/*' -not -path './release.json' -print0 \
  | LC_ALL=C sort -z \
  | xargs -0 sha256sum \
  | sha256sum | awk '{print \$1}'
REMOTE
}

# local_tree_sha: cùng phép đo, phía máy trạm, trên bản giải nén từ artifact.
local_tree_sha() {
  local tmp
  tmp="$(mktemp -d)"
  tar -xzf "$ARTIFACT" -C "$tmp"
  ( cd "$tmp" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 \
      | sed 's/  */  /' | shasum -a 256 | awk '{print $1}' )
  rm -rf "$tmp"
}

# write_release_json: metadata của bản phát hành, ĐẶT TRÊN MÁY CHỦ.
# Nó là bản ghi tiện tra, KHÔNG phải bằng chứng — xem remote_tree_sha.
write_release_json() {
  local release_id="$1" sha="$2" branch="$3" tree="$4"
  remote_sh <<REMOTE
cat > "$ENV_ROOT/releases/$release_id/release.json" <<'JSON'
{
  "project": "$PROJECT",
  "release_id": "$release_id",
  "git_sha": "$sha",
  "git_tree_sha": "$tree",
  "branch": "$branch",
  "built_at": "$(_ts)",
  "deployed_at_note": "deployed_at do máy chủ ghi ở dòng dưới",
  "environment": "$ENV_NAME",
  "artifact_sha256": "$ARTIFACT_SHA256"
}
JSON
# deployed_at phải là giờ của MÁY CHỦ, không phải giờ máy trạm.
python3 - "$ENV_ROOT/releases/$release_id/release.json" <<'PY'
import json,sys,datetime
p=sys.argv[1]
d=json.load(open(p))
d.pop("deployed_at_note",None)
d["deployed_at"]=datetime.datetime.now().astimezone().isoformat(timespec="seconds")
json.dump(d,open(p,"w"),ensure_ascii=False,indent=2)
PY
REMOTE
  done_or_dry "đã ghi release.json trên máy chủ"
}

# docker_run_release: build ảnh từ bản phát hành rồi chạy container.
# Không dùng `docker compose` vì host staging không cho sudo và compose không
# chắc có; `docker run` thì chắc chắn có nếu docker có.
docker_run_release() {
  local release_id="$1" port="$2" container="$3" network="$4" pg_container="$5"
  remote_sh <<REMOTE
ROOT="$ENV_ROOT"
REL="\$ROOT/releases/$release_id"
IMG="$PROJECT-$ENV_NAME:$release_id"

docker network inspect "$network" >/dev/null 2>&1 || docker network create "$network"

# PostgreSQL: chỉ tạo nếu chưa có. KHÔNG xoá, KHÔNG tạo lại — dữ liệu staging
# cũng là dữ liệu, và một lượt triển khai không có quyền làm mất nó.
if ! docker inspect "$pg_container" >/dev/null 2>&1; then
  echo "LỖI: chưa có container PostgreSQL '$pg_container'." >&2
  echo "     Tạo CSDL là việc một lần, do người làm, có mật khẩu — xem" >&2
  echo "     docs/DIRECT-DEPLOY.md §3. Script triển khai không tự tạo CSDL." >&2
  exit 1
fi

docker build -q -t "\$IMG" -f "\$REL/deploy/Dockerfile" "\$REL" >/dev/null
echo "đã build ảnh \$IMG"

# Chạy bản mới dưới TÊN TẠM, trên CỔNG TẠM, rồi mới đổi chỗ. Nhờ vậy bản đang
# chạy không bị tắt trước khi biết bản mới có khởi động được hay không.
TMPNAME="$container-new"
docker rm -f "\$TMPNAME" >/dev/null 2>&1 || true
docker run -d --name "\$TMPNAME" \
  --network "$network" \
  --env-file "\$ROOT/shared/.env" \
  -e RELEASE_ID="$release_id" \
  -e GIT_SHA="$(git_sha)" \
  -p "127.0.0.1:$ENV_TEMP_PORT:8000" \
  -v "$PROJECT-$ENV_NAME-media:/app/var/media" \
  --restart no \
  "\$IMG" >/dev/null
echo "đã chạy bản mới dưới tên tạm \$TMPNAME ở cổng $ENV_TEMP_PORT"
REMOTE
}

# docker_promote: bản tạm đã khoẻ → đổi nó thành bản chính thức.
docker_promote() {
  local release_id="$1" port="$2" container="$3" network="$4"
  remote_sh <<REMOTE
ROOT="$ENV_ROOT"
TMPNAME="$container-new"

# Bản đang chạy trở thành bản trước, để rollback có chỗ quay về.
PREVNAME=""
if docker inspect "$container" >/dev/null 2>&1; then
  PREVNAME="$container-prev-\$(date +%s)"
  docker rename "$container" "\$PREVNAME"
fi
# Dừng MỌI bản trước bằng bộ lọc của docker, KHÔNG bằng glob của shell: glob khớp
# TÊN FILE trong thư mục hiện tại chứ không phải tên container — bản cũ sẽ chạy
# tiếp, giữ cổng, và docker run dưới đây hỏng vì cổng đã bị chiếm (#86).
# (Không dùng dấu backtick trong heredoc này: nó KHÔNG có nháy, backtick sẽ bị chạy.)
docker ps -q --filter "name=^$container-prev-" | xargs -r docker stop >/dev/null
# mv -T: KHÔNG đi theo symlink đích. "mv -f a previous" khi previous là symlink tới
# một thư mục sẽ CHUYỂN a VÀO thư mục đó và previous đứng yên ở bản cũ hơn — rollback
# quay về sai bản (#88, đo trên bản sao staging).
[ -L "\$ROOT/current" ] && cp -P "\$ROOT/current" "\$ROOT/previous.tmp" && mv -Tf "\$ROOT/previous.tmp" "\$ROOT/previous"

docker stop "\$TMPNAME" >/dev/null
docker rm "\$TMPNAME" >/dev/null
IMG="$PROJECT-$ENV_NAME:$release_id"
if ! docker run -d --name "$container" \
  --network "$network" \
  --env-file "\$ROOT/shared/.env" \
  -e RELEASE_ID="$release_id" \
  -e GIT_SHA="$(git_sha)" \
  -p "127.0.0.1:$port:8000" \
  -v "$PROJECT-$ENV_NAME-media:/app/var/media" \
  --restart unless-stopped \
  "\$IMG" >/dev/null; then
  # Không bao giờ để môi trường không có bản nào chạy: dựng lại bản trước.
  echo "LỖI: không chạy được bản mới dưới tên chính thức — dựng lại bản trước" >&2
  docker rm -f "$container" >/dev/null 2>&1 || true
  if [ -n "\$PREVNAME" ]; then
    docker rename "\$PREVNAME" "$container" && docker start "$container" >/dev/null \
      && echo "đã dựng lại bản trước dưới tên $container" >&2
  fi
  exit 1
fi

# Chờ bản CHÍNH THỨC khoẻ trên cổng chính trước khi báo xong. Container vừa tạo
# chưa nghe ngay: không chờ thì verify.sh gọi ngay sau đó nhận 000 — và
# production.sh coi đó là hỏng rồi TỰ ROLLBACK (#88, đo trên bản sao staging).
healthy=0
for i in \$(seq 1 30); do
  code=\$(curl -s -o /dev/null -w '%{http_code}' -m 5 $(host_header) "http://127.0.0.1:$port$HEALTH_PATH" || true)
  if [ "\$code" = "200" ]; then healthy=1; break; fi
  sleep 2
done
if [ "\$healthy" != 1 ]; then
  echo "LỖI: bản chính thức không lên health 200 trên cổng $port — dựng lại bản trước" >&2
  docker logs --tail 30 "$container" 2>&1 | sed 's/^/    log| /' >&2
  docker rm -f "$container" >/dev/null 2>&1 || true
  if [ -n "\$PREVNAME" ]; then
    docker rename "\$PREVNAME" "$container" && docker start "$container" >/dev/null \
      && echo "đã dựng lại bản trước dưới tên $container" >&2
  fi
  exit 1
fi
echo "bản chính thức khoẻ trên cổng $port (lần thử \$i)"

ln -sfn "\$ROOT/releases/$release_id" "\$ROOT/current.tmp"
mv -Tf "\$ROOT/current.tmp" "\$ROOT/current"
printf '%s\t%s\t%s\t%s\n' "\$(date -Is)" "$ENV_NAME" "$release_id" "$(git_sha)" >> "\$ROOT/history.log"
echo "đã chuyển current → $release_id"
REMOTE
  done_or_dry "đã đổi bản đang chạy sang $release_id"
}

# remote_prune: giữ KEEP_RELEASES bản gần nhất, ngoài bản đang chạy và bản trước.
# Theo §19.4 của CLAUDE.md: xoá bản phát hành tự sinh là ngoại lệ hợp lệ của
# luật thùng rác, nhưng vẫn giữ theo SỐ BẢN, và không bao giờ xoá bản đang chạy.
remote_prune() {
  remote_sh <<REMOTE
ROOT="$ENV_ROOT"
CUR="\$(readlink "\$ROOT/current" 2>/dev/null | xargs -r basename || true)"
PREV="\$(readlink "\$ROOT/previous" 2>/dev/null | xargs -r basename || true)"
cd "\$ROOT/releases" || exit 0
ls -1t | tail -n +$((KEEP_RELEASES + 1)) | while read -r r; do
  [ "\$r" = "\$CUR" ] && continue
  [ "\$r" = "\$PREV" ] && continue
  rm -rf "\$r" && echo "đã dọn bản cũ: \$r"
done
REMOTE
}
