#!/usr/bin/env bash
# ============================================================================
# Sao lưu PostgreSQL staging theo CHÍNH SÁCH OWNER ĐÃ CHỐT:
#   - mỗi ngày 1 lần · giữ 14 bản ngày · giữ 4 bản tuần · kiểm phục hồi mỗi tháng
#
# ⚠️  GIỚI HẠN PHẢI BIẾT: script này lưu NGAY TRÊN MÁY STAGING. Mất máy là mất
#     cả database lẫn bản sao lưu. Đây là bước ĐẦU, KHÔNG phải phương án đủ.
#     Cần một đích KHÁC MÁY (NAS/VPS khác/object storage) — xem docs/backup-restore.md.
#
# TỪ CHỐI chạy nếu database trông giống production.
# ============================================================================
set -euo pipefail

CONTAINER="${CONTAINER:-vipphone-staging-pg}"
DBUSER="${DBUSER:-vipphone}"
DBNAME="${DBNAME:-vipphone_staging}"
DEST="${DEST:-$HOME/vipphone-staging/backups}"

case "$DBNAME" in *prod*) echo "TỪ CHỐI: tên database chứa 'prod' ($DBNAME)"; exit 2;; esac
mkdir -p "$DEST/daily" "$DEST/weekly"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST/daily/vipphone-$STAMP.dump"

docker exec "$CONTAINER" pg_dump -U "$DBUSER" -d "$DBNAME" -Fc -f "/tmp/bk.dump"
docker cp "$CONTAINER:/tmp/bk.dump" "$OUT" >/dev/null
docker exec "$CONTAINER" rm -f /tmp/bk.dump
chmod 600 "$OUT"
sha256sum "$OUT" > "$OUT.sha256"

# Giữ 14 bản ngày gần nhất
ls -1t "$DEST/daily"/vipphone-*.dump 2>/dev/null | tail -n +15 | while read -r f; do
  rm -f "$f" "$f.sha256"
done

# Chủ nhật hằng tuần: nhân bản sang weekly rồi giữ 4 bản
if [ "$(date -u +%u)" = "7" ]; then
  cp "$OUT" "$DEST/weekly/vipphone-weekly-$STAMP.dump"
  sha256sum "$DEST/weekly/vipphone-weekly-$STAMP.dump" > "$DEST/weekly/vipphone-weekly-$STAMP.dump.sha256"
  ls -1t "$DEST/weekly"/vipphone-weekly-*.dump 2>/dev/null | tail -n +5 | while read -r f; do
    rm -f "$f" "$f.sha256"
  done
fi

echo "OK $OUT ($(stat -c %s "$OUT") byte) · ngày:$(ls -1 "$DEST/daily" | grep -c '\.dump$') tuần:$(ls -1 "$DEST/weekly" 2>/dev/null | grep -c '\.dump$')"
