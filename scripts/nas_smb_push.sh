#!/bin/sh
# =============================================================================
# Chép bản sao lưu staging lên NAS bằng smbclient — CHẠY TRONG CONTAINER, do
# scripts/staging_backup.sh gọi (không chạy tay). POSIX sh (ảnh alpine).
#
#   nas_smb_push.sh <sub>/<tên-tệp> ...      (đường dẫn tương đối dưới /src)
#
# Môi trường: NAS_IP NAS_SHARE NAS_DIR KEEP_DAILY KEEP_WEEKLY; tài khoản ở /cred.
# Mỗi tệp: put vào tên tạm → rename → put .sha256 → TẢI LẠI và so sha256.
# "Đã chép" chỉ được nói sau khi bản TẢI VỀ TỪ NAS khớp mã băm — mã thoát của
# smbclient không đủ tin. Rồi xoay vòng trên NAS theo SỐ BẢN (tên có mốc giờ).
# Thoát 0 = mọi tệp khớp; 3 = có tệp không khớp / không chép được.
# =============================================================================
set -u
smb() { smbclient "//$NAS_IP/$NAS_SHARE" -A /cred "$@" 2>&1; }
RC=0

# Tạo cây thư mục (đã có thì smbclient báo trùng — bỏ qua có chủ ý, vì lần chép
# ngay sau đó sẽ tự lộ nếu thư mục thật sự không tạo được).
mkdir_p() {
  acc=""
  for part in $(echo "$1" | tr '/' ' '); do
    acc="${acc:+$acc/}$part"
    smb -c "mkdir \"$acc\"" >/dev/null || true
  done
}
mkdir_p "$NAS_DIR/daily"; mkdir_p "$NAS_DIR/weekly"

for rel in "$@"; do
  sub="${rel%%/*}"; name="${rel#*/}"
  want="$(cut -d' ' -f1 "/src/$rel.sha256")"
  smb -D "$NAS_DIR/$sub" -c "put \"/src/$rel\" \".$name.dang-chep\"; rename \".$name.dang-chep\" \"$name\"; put \"/src/$rel.sha256\" \"$name.sha256\"" >/dev/null
  rm -f /tmp/kiem
  smb -D "$NAS_DIR/$sub" -c "get \"$name\" /tmp/kiem" >/dev/null
  got="$( [ -f /tmp/kiem ] && sha256sum /tmp/kiem | cut -d' ' -f1 )"
  if [ -n "$got" ] && [ "$got" = "$want" ]; then
    echo "nas : $sub/$name sha256 khớp (tải lại từ NAS)"
  else
    echo "⚠ NAS: $sub/$name KHÔNG khớp (muốn ${want:-?}, NAS ${got:-không tải được})"; RC=3
  fi
done
rm -f /tmp/kiem

# Xoay vòng trên NAS: giữ N bản mới nhất theo tên (mốc giờ UTC trong tên ⇒ sắp theo tên = theo thời gian).
xoay() { # <sub> <mẫu ls> <tiền tố hợp lệ> <giữ>
  smb -D "$NAS_DIR/$1" -c "ls $2" | awk -v p="$3" '$1 ~ "^"p && $1 !~ /\.sha256$/ {print $1}' \
    | sort -r | tail -n +"$(( $4 + 1 ))" | while read -r f; do
      smb -D "$NAS_DIR/$1" -c "del \"$f\"; del \"$f.sha256\"" >/dev/null || true
      echo "nas : xoay vòng — xoá $1/$f"
    done
}
xoay daily  'vipphone-2*.dump'        'vipphone-2'        "$KEEP_DAILY"
xoay daily  'vipphone-media-*.tar.gz' 'vipphone-media-'   "$KEEP_DAILY"
xoay weekly 'vipphone-weekly-*.dump'  'vipphone-weekly-'  "$KEEP_WEEKLY"
exit "$RC"
