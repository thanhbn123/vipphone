#!/usr/bin/env bash
# ============================================================================
# Canh sức khoẻ staging VIP PHONE — chạy được ở đâu cũng được.
#
# VÌ SAO CÓ FILE NÀY: ngày 04/10/2026 máy chủ staging reboot. MỌI container đều
# tự sống lại — TRỪ PostgreSQL của vipphone, vì nó được tạo THIẾU cờ
# `--restart unless-stopped`. Hậu quả: DB chết 3 ngày mà không ai biết, vì
# `/api/health` vẫn 200 (nó chỉ kiểm tiến trình app), còn `/api/ready` mới là
# cái kiểm DB.
#
# Đây là lần hỏng thứ hai cùng kiểu (lần trước: thiếu `httpx` trong
# requirements.txt làm app crash-loop). Luật của vault §12.2: hỏng LẦN THỨ HAI
# cùng kiểu thì ĐỔI CẤU TRÚC, đừng chỉ sửa cho đúng thêm một lần.
# => Nên có phép ĐO ĐỘC LẬP thay vì trông vào việc có người nhớ kiểm.
#
# Dùng: bash scripts/staging_health_guard.sh [host] [user] [base_url]
# ============================================================================
set -uo pipefail

HOST="${1:-160.22.170.20}"
USER_="${2:-deploy}"
BASE="${3:-https://qua.viporder.vn}"
SSH=(ssh -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15 -i "$HOME/.ssh/id_ed25519" "$USER_@$HOST")

fail=0
say() { printf '  %-52s %s\n' "$1" "$2"; }

echo "=== 1. Chính sách restart (nguyên nhân gốc 04/10) ==="
for c in vipphone-staging-app vipphone-staging-pg; do
  p="$("${SSH[@]}" "docker inspect $c --format '{{.HostConfig.RestartPolicy.Name}}'" 2>/dev/null)"
  if [ "$p" = "unless-stopped" ]; then say "$c" "OK ($p)"
  else say "$c" "HỎNG: '$p' — phải là unless-stopped"; fail=1; fi
done

echo "=== 2. Container đang chạy ==="
for c in vipphone-staging-app vipphone-staging-pg; do
  s="$("${SSH[@]}" "docker inspect $c --format '{{.State.Status}}'" 2>/dev/null)"
  r="$("${SSH[@]}" "docker inspect $c --format '{{.RestartCount}}'" 2>/dev/null)"
  if [ "$s" = "running" ]; then say "$c" "OK (restart=$r)"
  else say "$c" "HỎNG: trạng thái '$s'"; fail=1; fi
done

echo "=== 3. DB đọc được + migration ==="
m="$("${SSH[@]}" 'docker exec -i vipphone-staging-pg psql -U vipphone -d vipphone_staging -tAc "SELECT version_num FROM alembic_version;"' 2>/dev/null | tr -d '[:space:]')"
if [ -n "$m" ]; then say "migration head" "OK ($m)"; else say "migration head" "HỎNG: không đọc được DB"; fail=1; fi

echo "=== 4. ỨNG DỤNG nói gì (đây mới là phép đo thật) ==="
h="$(curl -sS -m 15 -o /dev/null -w '%{http_code}' "$BASE/api/health" 2>/dev/null)"
rr="$(curl -sS -m 15 -o /dev/null -w '%{http_code}' "$BASE/api/ready" 2>/dev/null)"
[ "$h" = "200" ]  && say "GET /api/health" "OK (200)"  || { say "GET /api/health" "HỎNG: $h"; fail=1; }
# `ready` là cái DUY NHẤT phát hiện ra DB chết. `health` không phát hiện được.
[ "$rr" = "200" ] && say "GET /api/ready"  "OK (200)"  || { say "GET /api/ready"  "HỎNG: $rr (DB có thể đã chết)"; fail=1; }

echo
if [ "$fail" -eq 0 ]; then echo "KẾT QUẢ: ĐẠT"; else echo "KẾT QUẢ: KHÔNG ĐẠT — xem dòng HỎNG ở trên"; fi
exit "$fail"
