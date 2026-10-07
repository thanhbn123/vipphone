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
#
# BA CHECK `E2E (...)` ĐÃ ĐƯỢC GỠ KHỎI DANH SÁCH NÀY — 07/10/2026, anh Thành duyệt.
#
# Vì sao: từ bộ triển khai trực tiếp (docs/DIRECT-DEPLOY.md §8), job `e2e` trong
# .github/workflows/ci.yml chỉ chạy khi `workflow_dispatch`. Nó KHÔNG xuất hiện
# trên pull request nữa. Giữ ba tên đó làm check bắt buộc thì GitHub sẽ chờ mãi
# ba check không bao giờ tới, và **không PR nào merge được** — đúng cái lỗi mà
# chú thích ngay trên đã cảnh báo, chỉ là lần này do chính ta gây ra.
#
# Độ phủ E2E không mất: `make test-e2e` tại máy, và `deploy/verify.sh` đo trên
# bản ĐANG CHẠY. Muốn E2E thành check bắt buộc lại thì bỏ dòng `if:` của job
# `e2e` TRƯỚC, rồi mới thêm ba tên này lại vào đây — theo thứ tự đó, không
# ngược lại.
CHECKS=(
  "Backend (lint, migration, tests)"
  "Dependency scan (pip-audit)"
  "Secret scan (gitleaks)"
  "Validate static frontend"
)

# ---------------------------------------------------------------------------
# CHỐT CHẶN: danh sách viết tay ở trên phải KHỚP thực tế trước khi áp dụng.
#
# Đây là lần thứ hai cùng một kiểu hỏng (danh sách tên check viết tay lệch với
# tên job thật), nên theo §12.2 của CLAUDE.md thì phải ĐỔI CẤU TRÚC, đừng sửa
# cho đúng thêm một lần nữa: từ nay máy tự đối chiếu, không dựa vào việc người
# sửa có nhớ hay không.
#
# Cố ý KHÔNG tự sinh danh sách từ API: danh sách check bắt buộc là một lời
# tuyên bố có chủ ý. Nếu tự sinh, một lượt CI chạy thiếu job sẽ âm thầm làm
# branch protection YẾU đi — bỏ sót ở đây là bỏ sót theo chiều nguy hiểm.
# Vậy nên: người viết danh sách, máy kiểm danh sách.
# ---------------------------------------------------------------------------
preflight_checks() {
  local branch="${1:-develop}" seen missing=0 extra
  if ! seen=$(gh api "repos/$REPO/commits/$branch/check-runs" \
                --jq '.check_runs[].name' 2>/dev/null | sort -u); then
    echo "DỪNG: không đọc được check-runs của $branch (gh auth? nhánh chưa có CI?)." >&2
    echo "      KHÔNG áp dụng branch protection khi chưa đối chiếu được danh sách." >&2
    return 1
  fi
  if [ -z "$seen" ]; then
    echo "DỪNG: $branch chưa có check-run nào ⇒ không có gì để đối chiếu." >&2
    return 1
  fi

  for c in "${CHECKS[@]}"; do
    if ! printf '%s\n' "$seen" | grep -Fxq "$c"; then
      echo "  THIẾU: \"$c\" không có trong check-runs của $branch" >&2
      missing=1
    fi
  done
  if [ "$missing" -ne 0 ]; then
    echo "DỪNG: có check bắt buộc không bao giờ xuất hiện ⇒ PR sẽ chờ mãi." >&2
    echo "      Sửa CHECKS ở đầu script cho khớp tên job thật rồi chạy lại." >&2
    return 1
  fi

  # Job mới xuất hiện mà chưa được liệt kê: CẢNH BÁO, không chặn. Thiếu một
  # check bắt buộc chỉ làm bảo vệ yếu hơn, không làm PR kẹt — nên nó không được
  # phép khoá tay người đang chạy script, nhưng phải nói ra.
  extra=$(printf '%s\n' "$seen" | grep -Fxv -f <(printf '%s\n' "${CHECKS[@]}") || true)
  if [ -n "$extra" ]; then
    echo "  LƯU Ý: $branch có check KHÔNG nằm trong danh sách bắt buộc:" >&2
    printf '%s\n' "$extra" | sed 's/^/           /' >&2
    echo "         (job chạy tay như E2E thì đúng là phải nằm ngoài — xem chú thích trên)" >&2
  fi
  echo "  đối chiếu danh sách: ${#CHECKS[@]}/${#CHECKS[@]} check bắt buộc có thật trên $branch"
}

build_json() {
  # Dùng JSON BODY, không dùng -f/-F.
  #
  # VÌ SAO: endpoint branch protection của GitHub có schema `anyOf`, và khi gửi
  # bằng tham số rời thì nó đòi `restrictions` phải có mặt tường minh —
  #   `"restrictions" wasn't supplied. (HTTP 422)`
  # Gửi JSON đầy đủ (kể cả `"restrictions": null`) là dạng chạy được.
  #
  # Hai lỗi ĐÃ DÍNH khi chạy thật, ghi lại để không ai lặp:
  #   1. `-f 'required_status_checks[strict]=true'` -> gửi CHUỖI "true" ->
  #      422 `For 'properties/strict', "true" is not a boolean`. Phải dùng `-F`.
  #   2. Kể cả khi đã dùng `-F`, vẫn 422 vì thiếu `restrictions`.
  local branch="$1"
  local contexts
  contexts=$(printf '%s\n' "${CHECKS[@]}" | jq -R . | jq -s .)
  jq -n \
    --argjson contexts "$contexts" \
    '{
       required_status_checks: { strict: true, contexts: $contexts },
       enforce_admins: false,
       required_pull_request_reviews: { required_approving_review_count: 0 },
       restrictions: null,
       allow_force_pushes: false,
       allow_deletions: false
     }'
}

apply_branch() {
  local branch="$1"
  build_json "$branch" | gh api -X PUT "repos/$REPO/branches/$branch/protection" \
    -H "Accept: application/vnd.github+json" --input - >/dev/null
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

echo "=== ĐỐI CHIẾU DANH SÁCH CHECK BẮT BUỘC VỚI THỰC TẾ ==="
# Chạy ở CẢ HAI chế độ: ở chế độ chỉ in, Owner thấy trước khi dán lệnh đi đâu.
# Ở chế độ --apply, nó là cửa khoá: không khớp thì KHÔNG áp dụng.
PREFLIGHT_OK=1
preflight_checks develop || PREFLIGHT_OK=0
echo

if [ "$APPLY" -eq 0 ]; then
  echo "=== CHẾ ĐỘ CHỈ IN — chưa gọi GitHub lần nào (ngoài lượt đọc check-runs ở trên) ==="
  [ "$PREFLIGHT_OK" -eq 1 ] || echo "⚠️  ĐỐI CHIẾU KHÔNG ĐẠT — đừng dán lệnh dưới đây trước khi sửa CHECKS."
  echo "Chạy lại với --apply để thực sự áp dụng."
  echo
  # In ra dạng COPY-PASTE ĐƯỢC. Không dùng `printf %q` vì nó mã hoá ký tự
  # tiếng Việt thành $'...' và làm hỏng tên check khi Owner dán lại.
  for b in main develop; do
    echo "# ----- $b -----"
    echo "gh api -X PUT repos/$REPO/branches/$b/protection \\"
    echo "  -H 'Accept: application/vnd.github+json' --input - <<'JSON'"
    build_json "$b" | sed 's/^/  /'
    echo "JSON"
    echo
  done
  exit 0
fi

if [ "$PREFLIGHT_OK" -ne 1 ]; then
  echo "DỪNG: đối chiếu danh sách check KHÔNG đạt (xem ngay trên)." >&2
  echo "      Áp dụng lúc này sẽ làm mọi PR chờ mãi một check không bao giờ tới." >&2
  exit 1
fi

echo "=== ÁP DỤNG THẬT ==="
for b in main develop; do
  echo "  -> $b"
  apply_branch "$b"
done

echo
echo "=== KIỂM LẠI ==="
for b in main develop; do
  gh api "repos/$REPO/branches/$b/protection" --jq \
    "\"  $b: strict=\(.required_status_checks.strict) checks=\(.required_status_checks.contexts|length) force_push=\(.allow_force_pushes.enabled) deletions=\(.allow_deletions.enabled)\""
done
