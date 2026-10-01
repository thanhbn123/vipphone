#!/usr/bin/env bash
# Kiểm tra trước khi deploy staging. Toàn bộ logic nằm ở staging_preflight.py
# (dễ viết đúng và dễ kiểm hơn bash). Đây chỉ là cửa vào theo tên quy ước.
#
#   scripts/staging_preflight.sh                     # đọc biến từ môi trường
#   scripts/staging_preflight.sh --env-file .env     # nạp thêm từ file
#   scripts/staging_preflight.sh --static-only       # không cần DB/mạng
#
# Thoát mã 0 nếu ĐẠT, 1 nếu có mục FAIL.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"

# Ưu tiên Python của venv (có psycopg + alembic); thiếu thì dùng python3 hệ thống.
if [ -x "$REPO/.venv/bin/python" ]; then
  PY="$REPO/.venv/bin/python"
else
  PY="$(command -v python3 || true)"
fi

if [ -z "$PY" ]; then
  echo "LỖI: không tìm thấy Python 3." >&2
  exit 1
fi

exec "$PY" "$HERE/staging_preflight.py" "$@"
