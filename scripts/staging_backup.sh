#!/usr/bin/env bash
# ============================================================================
# Sao lưu staging CHẠY TRÊN MÁY CHỦ (cron của user deploy) theo CHÍNH SÁCH OWNER (D-005):
#   - mỗi ngày 1 lần · giữ 14 bản ngày · giữ 4 bản tuần · kiểm phục hồi mỗi tháng
#
# Mỗi lượt: (1) pg_dump -Fc + kiểm đọc được · (2) ảnh sản phẩm (volume media) · (3) sha256
#           (4) CHÉP SANG NAS (khác máy) và so sha256 hai đầu · (5) xoay vòng cả hai nơi.
#
# NAS: /mnt/vip-nas do root gắn một lần (CIFS qua Tailscale, uid=deploy) — xem
#   docs/backup-restore.md. Chỉ coi là "đã gắn" khi NAS_MOUNT là ĐIỂM GẮN THẬT
#   (mountpoint -q), không phải "thư mục có tồn tại": chưa gắn mà ghi vào thì bản
#   "trên NAS" thật ra nằm trên chính đĩa staging — hỏng im lặng.
#   NAS chưa gắn / chép lệch ⇒ bản trên máy VẪN giữ, in cảnh báo, THOÁT MÃ 3.
#
# TỪ CHỐI chạy nếu database trông giống production.
# ============================================================================
set -euo pipefail

CONTAINER="${CONTAINER:-vipphone-staging-pg}"
DBUSER="${DBUSER:-vipphone}"
DBNAME="${DBNAME:-vipphone_staging}"
MEDIA_VOL="${MEDIA_VOL:-vipphone-staging-media}"
DEST="${DEST:-$HOME/vipphone-staging/backups}"
NAS_MOUNT="${NAS_MOUNT:-/mnt/vip-nas}"
NAS_DEST="${NAS_DEST:-$NAS_MOUNT/vip-vault/viporder-staging/vipphone}"
KEEP_DAILY="${KEEP_DAILY:-14}"
KEEP_WEEKLY="${KEEP_WEEKLY:-4}"

case "$DBNAME" in *prod*) echo "TỪ CHỐI: tên database chứa 'prod' ($DBNAME)"; exit 2;; esac
mkdir -p "$DEST/daily" "$DEST/weekly"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST/daily/vipphone-$STAMP.dump"
MEDIA="$DEST/daily/vipphone-media-$STAMP.tar.gz"
echo "== sao lưu staging $STAMP ($(date '+%Y-%m-%d %H:%M:%S %z'))"

# 1. Database + kiểm ĐỌC ĐƯỢC (file dump hỏng vẫn có kích thước).
docker exec "$CONTAINER" pg_dump -U "$DBUSER" -d "$DBNAME" -Fc -f /tmp/bk.dump
docker cp "$CONTAINER:/tmp/bk.dump" "$OUT" >/dev/null
docker exec "$CONTAINER" pg_restore --list /tmp/bk.dump >/dev/null \
  || { echo "LỖI: pg_restore --list không đọc được bản dump" >&2; docker exec "$CONTAINER" rm -f /tmp/bk.dump; exit 1; }
docker exec "$CONTAINER" rm -f /tmp/bk.dump
chmod 600 "$OUT"
( cd "$DEST/daily" && sha256sum "$(basename "$OUT")" > "$(basename "$OUT").sha256" )
echo "db   : $(basename "$OUT") $(stat -c %s "$OUT") byte, pg_restore --list sạch"

# 2. Ảnh sản phẩm (volume media). Stream ra stdout ⇒ file thuộc deploy, không thuộc root.
if docker volume inspect "$MEDIA_VOL" >/dev/null 2>&1; then
  IMG="$(docker inspect -f '{{.Config.Image}}' "$CONTAINER")"
  docker run --rm --network none -v "$MEDIA_VOL:/m:ro" "$IMG" tar -czf - -C /m . > "$MEDIA"
  chmod 600 "$MEDIA"
  tar -tzf "$MEDIA" >/dev/null || { echo "LỖI: bản sao lưu ảnh không đọc lại được" >&2; exit 1; }
  ( cd "$DEST/daily" && sha256sum "$(basename "$MEDIA")" > "$(basename "$MEDIA").sha256" )
  echo "ảnh : $(basename "$MEDIA") — $(tar -tzf "$MEDIA" | grep -vc '/$' || true) tệp"
else
  MEDIA=""; echo "ảnh : không có volume $MEDIA_VOL — bỏ qua"
fi

# 3. Bản tuần (Chủ nhật, UTC).
WEEKLY=""
if [ "$(date -u +%u)" = "7" ]; then
  WEEKLY="$DEST/weekly/vipphone-weekly-$STAMP.dump"
  cp "$OUT" "$WEEKLY"
  ( cd "$DEST/weekly" && sha256sum "$(basename "$WEEKLY")" > "$(basename "$WEEKLY").sha256" )
fi

# Xoay vòng một thư mục theo SỐ BẢN (không theo tuổi): giữ N bản mới nhất của mẫu.
xoay() { # <thư mục> <mẫu> <giữ>
  # `|| true` BẮT BUỘC: thư mục chưa có bản nào (ví dụ weekly trước Chủ nhật đầu tiên) thì
  # ls trả mã ≠ 0, và với pipefail + set -e script chết IM LẶNG ngay đây — đo được khi thử.
  { ls -1t "$1"/$2 2>/dev/null || true; } | tail -n +"$(( $3 + 1 ))" | while read -r f; do rm -f "$f" "$f.sha256"; done
}
xoay "$DEST/daily"  'vipphone-2*.dump'          "$KEEP_DAILY"
xoay "$DEST/daily"  'vipphone-media-*.tar.gz'   "$KEEP_DAILY"
xoay "$DEST/weekly" 'vipphone-weekly-*.dump'    "$KEEP_WEEKLY"

# 4. Chép sang NAS + so sha256 hai đầu.
NAS_RC=0
if ! mountpoint -q "$NAS_MOUNT"; then
  echo "⚠ NAS CHƯA GẮN ($NAS_MOUNT không phải điểm gắn) — bản sao lưu CHỈ nằm trên máy staging."
  NAS_RC=3
else
  mkdir -p "$NAS_DEST/daily" "$NAS_DEST/weekly"
  for f in "$OUT" ${MEDIA:+"$MEDIA"} ${WEEKLY:+"$WEEKLY"}; do
    sub="$(basename "$(dirname "$f")")"
    cp "$f" "$NAS_DEST/$sub/.$(basename "$f").dang-chep"
    mv "$NAS_DEST/$sub/.$(basename "$f").dang-chep" "$NAS_DEST/$sub/$(basename "$f")"
    cp "$f.sha256" "$NAS_DEST/$sub/"
    if ( cd "$NAS_DEST/$sub" && sha256sum -c --quiet "$(basename "$f").sha256" ); then
      echo "nas : $sub/$(basename "$f") sha256 khớp"
    else
      echo "⚠ NAS: sha256 LỆCH ở $sub/$(basename "$f")"; NAS_RC=3
    fi
  done
  xoay "$NAS_DEST/daily"  'vipphone-2*.dump'        "$KEEP_DAILY"
  xoay "$NAS_DEST/daily"  'vipphone-media-*.tar.gz' "$KEEP_DAILY"
  xoay "$NAS_DEST/weekly" 'vipphone-weekly-*.dump'  "$KEEP_WEEKLY"
fi

dem() { local n=0 f; for f in "$1"/$2; do [ -e "$f" ] && n=$((n+1)); done; echo "$n"; }
if [ "$NAS_RC" = 0 ]; then KQ="OK — máy + NAS"; else KQ="CHỈ TRÊN MÁY (mã 3)"; fi
echo "KẾT QUẢ: $KQ · ngày:$(dem "$DEST/daily" 'vipphone-2*.dump') tuần:$(dem "$DEST/weekly" 'vipphone-weekly-*.dump')"
exit "$NAS_RC"
