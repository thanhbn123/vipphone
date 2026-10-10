#!/usr/bin/env bash
# ============================================================================
# DIỄN TẬP PHỤC HỒI TỪ NAS — chạy TRÊN MÁY STAGING (cron hằng tháng của deploy, D-005).
#
# Bản sao lưu ngoài máy mà chưa từng phục hồi thử thì chưa chứng minh được gì. Script:
#   1. tải bản dump MỚI NHẤT + .sha256 từ NAS (smbclient qua container Tailscale,
#      cùng đường (b) của scripts/staging_backup.sh) vào thư mục tạm;
#   2. so sha256 — lệch thì DỪNG;
#   3. restore_drill.py --from-dump: phục hồi vào database TẠM MỚI (không bao giờ
#      đè database đang chạy), kiểm head + bảng quan trọng, xoá database tạm;
#   4. in tổng thời gian tải + phục hồi = số đo RTO thật (mục tiêu D-005: 4 giờ).
# Tệp dump tạm (có PII) bị xoá dù thành công hay hỏng.
# Thoát 0 = PASS; 1 = phục hồi hỏng; 3 = không lấy được bản từ NAS / lệch sha256.
# ============================================================================
set -euo pipefail

NAS_TS_CONTAINER="${NAS_TS_CONTAINER:-vipphone-tailscale}"
NAS_CRED="${NAS_CRED:-$HOME/.config/vip-nas/cred}"
NAS_IP="${NAS_IP:-100.120.9.63}"
NAS_SHARE="${NAS_SHARE:-data}"
NAS_DIR="${NAS_DIR:-vip-vault/viporder-staging/vipphone}"
SMB_IMG="${SMB_IMG:-vipphone-smbclient:alpine3.20}"
PG_CONTAINER="${PG_CONTAINER:-vipphone-staging-pg}"
DBNAME="${DBNAME:-vipphone_staging}"
DBUSER="${DBUSER:-vipphone}"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "== diễn tập phục hồi từ NAS ($(date '+%Y-%m-%d %H:%M:%S %z'))"
if [ ! -s "$NAS_CRED" ]; then echo "KẾT QUẢ: FAIL — thiếu tài khoản NAS $NAS_CRED"; exit 3; fi
if [ "$(docker inspect -f '{{.State.Running}}' "$NAS_TS_CONTAINER" 2>/dev/null)" != true ]; then
  echo "KẾT QUẢ: FAIL — container Tailscale $NAS_TS_CONTAINER không chạy ⇒ không tới được NAS"; exit 3
fi
BAT_DAU=$(date +%s)
TMP="$(mktemp -d "$HOME/.nas-restore-drill-XXXXXX")"
trap 'rm -rf -- "${TMP:?}"' EXIT
chmod 700 "$TMP"

smb() {
  docker run --rm --network "container:$NAS_TS_CONTAINER" \
    -v "$NAS_CRED:/cred:ro" -v "$TMP:/out" -w /out "$SMB_IMG" \
    smbclient "//$NAS_IP/$NAS_SHARE" -A /cred -D "$NAS_DIR/daily" -c "$1" 2>&1
}

# 1. Bản mới nhất (tên có mốc giờ UTC ⇒ sắp theo tên = theo thời gian).
# `|| true`: smbclient trả mã ≠ 0 khi thư mục/tệp không có; với pipefail + set -e
# script sẽ chết IM LẶNG ngay trong phép gán (đo được khi thử). Thiếu thì báo bên dưới.
MOI="$( { smb 'ls vipphone-2*.dump' || true; } | awk '$1 ~ /^vipphone-2.*\.dump$/ {print $1}' | sort | tail -1)"
if [ -z "$MOI" ]; then
  echo "KẾT QUẢ: FAIL — không thấy bản dump nào trên NAS ($NAS_DIR/daily)"; exit 3
fi
smb "get \"$MOI\"; get \"$MOI.sha256\"" >/dev/null || true
if [ ! -s "$TMP/$MOI" ] || [ ! -s "$TMP/$MOI.sha256" ]; then
  echo "KẾT QUẢ: FAIL — không tải được $MOI (hoặc .sha256) từ NAS"; exit 3
fi
echo "1. tải từ NAS: $MOI ($(stat -c %s "$TMP/$MOI" 2>/dev/null || echo 0) byte) trong $(( $(date +%s) - BAT_DAU ))s"

# 2. sha256.
if ! ( cd "$TMP" && sha256sum -c --quiet "$MOI.sha256" ); then
  echo "KẾT QUẢ: FAIL — sha256 của bản tải từ NAS KHÔNG khớp"; exit 3
fi
echo "2. sha256 khớp"

# 3. Phục hồi vào database tạm.
echo "3. phục hồi"
RC=0
python3 -I "$HERE/restore_drill.py" --docker-pg "$PG_CONTAINER" --db "$DBNAME" --user "$DBUSER" \
  --from-dump "$TMP/$MOI" || RC=$?

# 4. RTO đo được.
echo "4. tổng thời gian tải + kiểm + phục hồi: $(( $(date +%s) - BAT_DAU ))s (mục tiêu D-005: 14400s)"
exit "$RC"
