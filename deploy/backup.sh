#!/usr/bin/env bash
# =============================================================================
# SAO LƯU trước khi triển khai — VIP PHONE
#   ./deploy/backup.sh staging|production
# =============================================================================
# Sao lưu năm thứ:
#   1. database  — pg_dump -Fc (dạng nén, phục hồi chọn lọc được)
#   2. dữ liệu bền — <ENV_ROOT>/shared/data nếu có
#   2b. ảnh sản phẩm — Docker volume <PROJECT>-<ENV>-media nếu có (D-010)
#   3. cấu hình cần thiết — DANH SÁCH BIẾN trong shared/.env (chỉ TÊN, không giá trị)
#   4. metadata bản đang chạy — current/release.json + history.log
#
# KHÔNG chép secret vào Git và KHÔNG tải secret về máy trạm. Bản sao lưu nằm
# trên máy chủ; đưa nó ra khỏi máy là việc riêng, xem docs/DIRECT-DEPLOY.md §5.
# =============================================================================
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
load_conf
select_env "${1:-}"
require_host

STAMP="$(date +%Y%m%d-%H%M%S)"
case "$ENV_NAME" in
  staging)    PG_CONTAINER="$STAGING_PG_CONTAINER";    PG_DB="$STAGING_PG_DB";    PG_USER="$STAGING_PG_USER" ;;
  production) PG_CONTAINER="$PRODUCTION_PG_CONTAINER"; PG_DB="$PRODUCTION_PG_DB"; PG_USER="$PRODUCTION_PG_USER" ;;
esac

step "SAO LƯU $ENV_NAME — $STAMP"

remote_sh <<REMOTE
ROOT="$ENV_ROOT"
DEST="\$ROOT/backups/$STAMP"
mkdir -p "\$DEST"

# 1. Database. Dùng -Fc: với CSDL lớn thì đây là dạng phục hồi song song được.
if ! docker inspect "$PG_CONTAINER" >/dev/null 2>&1; then
  echo "LỖI: không thấy container CSDL '$PG_CONTAINER' — không sao lưu được." >&2
  exit 1
fi
docker exec "$PG_CONTAINER" pg_dump -U "$PG_USER" -d "$PG_DB" -Fc -f /tmp/bk.dump
docker cp "$PG_CONTAINER:/tmp/bk.dump" "\$DEST/$PG_DB-$STAMP.dump" >/dev/null
docker exec "$PG_CONTAINER" rm -f /tmp/bk.dump
chmod 600 "\$DEST/$PG_DB-$STAMP.dump"
sha256sum "\$DEST/$PG_DB-$STAMP.dump" > "\$DEST/$PG_DB-$STAMP.dump.sha256"

# Kiểm bản dump ĐỌC ĐƯỢC, không chỉ kiểm file có tồn tại. Một file dump hỏng
# vẫn là một file có kích thước — và sẽ chỉ lộ ra đúng lúc cần phục hồi.
docker cp "\$DEST/$PG_DB-$STAMP.dump" "$PG_CONTAINER:/tmp/verify.dump" >/dev/null
if docker exec "$PG_CONTAINER" pg_restore --list /tmp/verify.dump >/dev/null 2>&1; then
  echo "dump đọc được: pg_restore --list chạy sạch"
else
  echo "LỖI: pg_restore --list KHÔNG đọc được bản dump vừa tạo." >&2
  docker exec "$PG_CONTAINER" rm -f /tmp/verify.dump || true
  exit 1
fi
docker exec "$PG_CONTAINER" rm -f /tmp/verify.dump

# 2. Dữ liệu bền (nếu dự án có).
if [ -d "\$ROOT/shared/data" ]; then
  tar -czf "\$DEST/shared-data-$STAMP.tar.gz" -C "\$ROOT/shared" data
  sha256sum "\$DEST/shared-data-$STAMP.tar.gz" > "\$DEST/shared-data-$STAMP.tar.gz.sha256"
fi

# 2b. Ảnh sản phẩm — Docker named volume mà container ứng dụng gắn vào /app/var/media.
#     Trước 2026-10-10 bước này KHÔNG có: DB phục hồi được nhưng ảnh thì mất (D-010).
#     Stream tar ra stdout để file do CHÍNH user deploy tạo (container ghi thẳng vào
#     thư mục gắn thì file thuộc root, deploy không xoá/xoay vòng được về sau).
#     Dùng lại ảnh của container CSDL (chắc chắn có trên máy, có tar), không kéo ảnh mới.
MEDIA_VOL="$PROJECT-$ENV_NAME-media"
if docker volume inspect "\$MEDIA_VOL" >/dev/null 2>&1; then
  IMG="\$(docker inspect -f '{{.Config.Image}}' "$PG_CONTAINER")"
  MEDIA_TAR="\$DEST/media-$STAMP.tar.gz"
  docker run --rm --network none -v "\$MEDIA_VOL:/m:ro" "\$IMG" tar -czf - -C /m . > "\$MEDIA_TAR"
  chmod 600 "\$MEDIA_TAR"
  if ! tar -tzf "\$MEDIA_TAR" >/dev/null 2>&1; then
    echo "LỖI: bản sao lưu ảnh \$MEDIA_TAR KHÔNG đọc lại được." >&2
    exit 1
  fi
  N_ANH="\$(tar -tzf "\$MEDIA_TAR" | grep -vc '/\$' || true)"
  sha256sum "\$MEDIA_TAR" > "\$MEDIA_TAR.sha256"
  echo "ảnh: volume \$MEDIA_VOL ⇒ \$N_ANH tệp, tar đọc lại được"
else
  echo "ảnh: không có volume \$MEDIA_VOL — bỏ qua (chưa từng chạy bản có ảnh)"
fi

# 3. Cấu hình: CHỈ TÊN BIẾN. Giá trị là secret và cố ý không được sao lưu ở đây
#    — bản sao lưu secret phải là việc có chủ ý, có nơi cất riêng.
if [ -f "\$ROOT/shared/.env" ]; then
  grep -oE '^[A-Z_]+' "\$ROOT/shared/.env" | sort > "\$DEST/env-keys.txt" || true
fi

# 4. Metadata bản đang chạy.
[ -f "\$ROOT/current/release.json" ] && cp "\$ROOT/current/release.json" "\$DEST/release-dang-chay.json"
[ -f "\$ROOT/history.log" ] && tail -50 "\$ROOT/history.log" > "\$DEST/history-tail.log"

du -sh "\$DEST" | awk '{print "kích thước bản sao lưu: " \$1}'
echo "BACKUP_DIR=\$DEST"
REMOTE

done_or_dry "sao lưu $ENV_NAME xong: $ENV_ROOT/backups/$STAMP"
