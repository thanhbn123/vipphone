#!/usr/bin/env bash
# ============================================================================
# Bật branch protection cho thanhbn123/vipphone — DÀNH CHO OWNER CHẠY.
#
# ⚠️  HARNESS KHÔNG TỰ CHẠY SCRIPT NÀY. Đây là thao tác chính sách, không phải
#     việc kỹ thuật. Xem docs/OWNER_DECISIONS_REQUIRED.md mục D-003.
#
# Mặc định script chỉ IN RA lệnh rồi thoát — không đụng gì tới GitHub.
# Muốn thực sự áp dụng thì thêm --apply.
#
#   ./scripts/enable_branch_protection.sh            # chỉ in
#   ./scripts/enable_branch_protection.sh --apply    # áp dụng thật
#
# Trước khi chạy: đảm bảo `gh auth status` đang đăng nhập tài khoản có quyền admin.
# ============================================================================
set -euo pipefail

REPO="${REPO:-thanhbn123/vipphone}"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

# Tên check PHẢI khớp CHÍNH XÁC tên job trong CI, nếu không GitHub sẽ chờ mãi một
# check không bao giờ xuất hiện và PR không merge được. Lấy bằng:
#   gh api repos/$REPO/commits/develop/check-runs --jq '.check_runs[].name' | sort -u
CHECKS=(
  "Backend (lint, migration, tests)"
  "Dependency scan (pip-audit)"
  "E2E (Chromium thật + PostgreSQL)"
  "Secret scan (gitleaks)"
  "Validate static frontend"
)

build_args() {
  local branch="$1"
  ARGS=(api -X PUT "repos/$REPO/branches/$branch/protection"
        -H "Accept: application/vnd.github+json"
        -f "required_status_checks[strict]=true")
  for c in "${CHECKS[@]}"; do
    ARGS+=(-f "required_status_checks[contexts][]=$c")
  done
  ARGS+=(
    -F "enforce_admins=false"                        # đổi thành true nếu muốn chặt nhất
    -F "required_pull_request_reviews[required_approving_review_count]=0"
    -F "allow_force_pushes=false"
    -F "allow_deletions=false"
  )
}

echo "=== Trạng thái HIỆN TẠI ==="
for b in main develop; do
  if gh api "repos/$REPO/branches/$b/protection" >/dev/null 2>&1; then
    echo "  $b: ĐANG được bảo vệ"
  else
    echo "  $b: CHƯA được bảo vệ"
  fi
done
echo

if [ "$APPLY" -eq 0 ]; then
  echo "=== CHẾ ĐỘ CHỈ IN — chưa gọi GitHub lần nào ==="
  echo "Chạy lại với --apply để thực sự áp dụng."
  echo
  # In ra dạng COPY-PASTE ĐƯỢC. Không dùng `printf %q` vì nó mã hoá ký tự
  # tiếng Việt thành $'...' và làm hỏng tên check khi Owner dán lại.
  for b in main develop; do
    echo "# ----- $b -----"
    echo "gh api -X PUT repos/$REPO/branches/$b/protection \\"
    echo "  -H 'Accept: application/vnd.github+json' \\"
    echo "  -f 'required_status_checks[strict]=true' \\"
    for c in "${CHECKS[@]}"; do
      echo "  -f 'required_status_checks[contexts][]=$c' \\"
    done
    echo "  -F 'enforce_admins=false' \\"
    echo "  -F 'required_pull_request_reviews[required_approving_review_count]=0' \\"
    echo "  -F 'allow_force_pushes=false' \\"
    echo "  -F 'allow_deletions=false'"
    echo
  done
  exit 0
fi

echo "=== ÁP DỤNG THẬT ==="
for b in main develop; do
  build_args "$b"
  echo "  -> $b"
  gh "${ARGS[@]}" >/dev/null
done

echo
echo "=== KIỂM LẠI ==="
for b in main develop; do
  gh api "repos/$REPO/branches/$b/protection" --jq \
    "\"  $b: strict=\(.required_status_checks.strict) checks=\(.required_status_checks.contexts|length) force_push=\(.allow_force_pushes.enabled) deletions=\(.allow_deletions.enabled)\""
done
