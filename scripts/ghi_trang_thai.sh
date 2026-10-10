# shellcheck shell=bash
# ============================================================================
# ghi_trang_thai <loai> <ma_thoat> <ghi_chu> — ghi trang-thai-<loai>.json trên máy
# rồi đẩy lên NAS (cạnh bản sao lưu). Được NẠP (source) bởi staging_backup.sh và
# nas_restore_drill.sh, gọi trong trap EXIT ⇒ chết giữa chừng vẫn có trạng thái.
#
# Bên đọc (bộ cảnh báo có Zalo, V-13452) chỉ cần đọc tệp trên NAS:
#   ket_qua != "ok"  ⇒ báo ngay;
#   luc_unix quá 26 giờ (sao-luu) / 32 ngày (phuc-hoi) ⇒ báo — bắt luôn ca chính
#   NAS hỏng (tệp không được cập nhật nữa) và ca cron không chạy.
# Không bao giờ làm hỏng lượt chạy: lỗi ghi trạng thái chỉ in ra, không đổi mã thoát.
# ============================================================================
ghi_trang_thai() {
  local loai="$1" ma="$2" ghi_chu="${3//[\"\\]/ }" ket_qua tep noi
  if [ "$ma" = 0 ]; then ket_qua=ok; else ket_qua=loi; fi
  noi="${TT_DIR:-$HOME/vipphone-staging/backups}"
  mkdir -p "$noi" 2>/dev/null || true
  tep="$noi/trang-thai-$loai.json"
  printf '{"du_an":"vipphone","moi_truong":"staging","may":"%s","loai":"%s","ket_qua":"%s","ma_thoat":%s,"luc":"%s","luc_unix":%s,"ghi_chu":"%s"}\n' \
    "$(hostname)" "$loai" "$ket_qua" "$ma" "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$(date +%s)" "$ghi_chu" > "$tep" 2>/dev/null \
    || { echo "trạng thái: KHÔNG ghi được $tep"; return 0; }
  # Đẩy lên NAS — cùng hai đường của staging_backup.sh.
  if mountpoint -q "${NAS_MOUNT:-/mnt/vip-nas}" && [ -n "${NAS_DEST:-}" ]; then
    mkdir -p "$NAS_DEST" 2>/dev/null && cp "$tep" "$NAS_DEST/" 2>/dev/null \
      && echo "trạng thái: $loai=$ket_qua → NAS (ổ gắn)" || echo "trạng thái: KHÔNG đẩy được lên NAS"
  elif [ -s "${NAS_CRED:-}" ] && [ "$(docker inspect -f '{{.State.Running}}' "${NAS_TS_CONTAINER:-}" 2>/dev/null)" = true ]; then
    if docker run --rm --network "container:$NAS_TS_CONTAINER" -v "$NAS_CRED:/cred:ro" -v "$tep:/tt.json:ro" "$SMB_IMG" \
        smbclient "//$NAS_IP/$NAS_SHARE" -A /cred -D "$NAS_DIR" -c "put /tt.json trang-thai-$loai.json" >/dev/null 2>&1; then
      echo "trạng thái: $loai=$ket_qua → NAS ($NAS_DIR/trang-thai-$loai.json)"
    else
      echo "trạng thái: KHÔNG đẩy được lên NAS (bên đọc sẽ thấy tệp cũ dần ⇒ vẫn báo)"
    fi
  else
    echo "trạng thái: NAS không sẵn sàng — chỉ ghi trên máy $tep"
  fi
  return 0
}
