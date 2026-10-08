#!/usr/bin/env bash
# =============================================================================
# TRIỂN KHAI PRODUCTION — VIP PHONE
#   ./deploy/production.sh                     triển khai bản đã PASS staging
#   DEPLOY_DRY_RUN=1 ./deploy/production.sh    in kế hoạch, không chạm máy chủ
# =============================================================================
# BA CỬA KHOÁ, cả ba fail closed:
#   1. Phải có phiếu staging PASS do verify.sh sinh ra, cho ĐÚNG SHA đang ở HEAD.
#   2. Cây làm việc phải sạch.
#   3. Gói đưa lên production phải TRÙNG MÃ BĂM với gói đã nghiệm thu ở staging
#      — không build lại từ một nguồn khác.
#
# Hỏng giữa đường thì KHÔNG sửa trực tiếp trên production: tự rollback, rồi sửa
# ở máy, test lại, deploy lại.
# =============================================================================
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
load_conf
select_env production

step "1. CỬA KHOÁ: CÂY LÀM VIỆC SẠCH"
require_clean_worktree
SHA="$(git_sha)"; BRANCH="$(git_branch)"; TREE="$(git_tree_sha)"
ok "nhánh $BRANCH · SHA $SHA"

step "2. CỬA KHOÁ: PHIẾU STAGING PASS CHO ĐÚNG SHA NÀY"
[ -d "$STATE_DIR/staging-pass" ] || die "chưa có phiếu staging nào. Chạy ./deploy/staging.sh rồi ./deploy/verify.sh staging"
GATE=""
for g in "$STATE_DIR/staging-pass"/*.json; do
  [ -f "$g" ] || continue
  if [ "$(json_str "$g" git_sha)" = "$SHA" ]; then GATE="$g"; fi
done
[ -n "$GATE" ] || die "không có phiếu staging PASS nào cho SHA $SHA.
     Production chỉ nhận bản ĐÃ nghiệm thu ở staging. Đây không phải thủ tục
     giấy tờ: nó là lý do một lỗi chỉ-staging (như STG-1, STG-2) không đi tiếp
     được vào production."
RELEASE_ID="$(json_str "$GATE" release_id)"
valid_release_id "$RELEASE_ID" || die "phiếu có release_id sai dạng: $RELEASE_ID"
ok "phiếu: $(basename "$GATE") · release $RELEASE_ID · nghiệm thu $(json_str "$GATE" verified_at)"

step "3. CỬA KHOÁ: GÓI PHẢI TRÙNG VỚI GÓI ĐÃ NGHIỆM THU"
AREC="$STATE_DIR/artifacts/$RELEASE_ID.json"
[ -f "$AREC" ] || die "thiếu sổ artifact $AREC — không chứng minh được đây là cùng một gói đã test ở staging"
EXPECT="$(json_str "$AREC" artifact_sha256)"
require_host
build_artifact "$RELEASE_ID" "$DEPLOY_DIR/artifacts"
[ "$ARTIFACT_SHA256" = "$EXPECT" ] || die "mã băm gói LỆCH với bản đã nghiệm thu ở staging.
     staging : $EXPECT
     vừa dựng: $ARTIFACT_SHA256
     Nghĩa là nguồn đã khác. KHÔNG đẩy lên production."
ok "gói trùng byte với gói đã PASS staging ($ARTIFACT_SHA256)"

step "4. GHI NHẬN BẢN ĐANG CHẠY (để rollback có đích)"
PREV="$(remote_capture <<REMOTE
readlink "$ENV_ROOT/current" 2>/dev/null | xargs -r basename || true
REMOTE
)"
PREV_SHA="$(remote_capture <<REMOTE
[ -f "$ENV_ROOT/current/release.json" ] && \
  sed -n 's/.*"git_sha"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$ENV_ROOT/current/release.json" | head -1 || true
REMOTE
)"
printf '  PREVIOUS_RELEASE : %s\n' "${PREV:-(chưa có bản nào)}"
printf '  PREVIOUS_SHA     : %s\n' "${PREV_SHA:-(chưa có)}"
mkdir -p "$STATE_DIR/production"
cat > "$STATE_DIR/production/previous.json" <<JSON
{
  "recorded_at": "$(_ts)",
  "previous_release": "${PREV:-}",
  "previous_sha": "${PREV_SHA:-}",
  "incoming_release": "$RELEASE_ID",
  "incoming_sha": "$SHA"
}
JSON

require_ports "$PRODUCTION_PORT" "$ENV_TEMP_PORT" "$PROJECT-prod-app"

step "5. SAO LƯU PRODUCTION"
"$DEPLOY_DIR/backup.sh" production

step "6. KIỂM MIGRATION"
migration_guard upgrade
PENDING="$(git -C "$REPO_ROOT" diff --name-only "${PREV_SHA:-$SHA}".."$SHA" -- migrations/versions 2>/dev/null | wc -l | tr -d ' ')"
if [ "${PENDING:-0}" -gt 0 ]; then
  warn "bản này có $PENDING file migration mới so với bản đang chạy"
  warn "rollback MÃ được, nhưng lược đồ thì KHÔNG tự hạ cấp — xem docs/DIRECT-DEPLOY.md §6"
else
  ok "không có migration mới so với bản đang chạy ⇒ rollback mã là đủ"
fi

step "7. ĐƯA BẢN LÊN PRODUCTION"
require_shared_env
ship_release "$RELEASE_ID"

step "8. MIGRATION TRÊN PRODUCTION"
remote_sh <<REMOTE
ROOT="$ENV_ROOT"
docker build -q -t "$PROJECT-$ENV_NAME:$RELEASE_ID" \
  -f "\$ROOT/releases/$RELEASE_ID/deploy/Dockerfile" "\$ROOT/releases/$RELEASE_ID" >/dev/null
docker run --rm --network "$PRODUCTION_NETWORK" --env-file "\$ROOT/shared/.env" \
  "$PROJECT-$ENV_NAME:$RELEASE_ID" alembic upgrade head
docker run --rm --network "$PRODUCTION_NETWORK" --env-file "\$ROOT/shared/.env" \
  "$PROJECT-$ENV_NAME:$RELEASE_ID" alembic check
REMOTE
done_or_dry "migration ở head, alembic check sạch"

step "9. CHẠY BẢN MỚI CẠNH BẢN CŨ"
docker_run_release "$RELEASE_ID" "$PRODUCTION_PORT" "$PROJECT-prod-app" "$PRODUCTION_NETWORK" "$PRODUCTION_PG_CONTAINER"

step "10. HEALTH BẢN MỚI — HỎNG THÌ DỪNG, KHÔNG ĐỔI"
if [ "${DEPLOY_DRY_RUN:-0}" = "1" ]; then
  warn "chạy khô: không gọi health"
else
  probe="$(remote_capture <<REMOTE
for i in \$(seq 1 30); do
  code=\$(curl -s -o /dev/null -w '%{http_code}' -m 5 $(host_header) "http://127.0.0.1:$ENV_TEMP_PORT$HEALTH_PATH" || echo 000)
  [ "\$code" = "200" ] && { echo "OK \$i"; exit 0; }
  sleep 2
done
echo "FAIL \$code"
docker logs --tail 40 "$PROJECT-prod-app-new" 2>&1 | sed 's/^/    log| /'
exit 1
REMOTE
)" || {
    printf '%s\n' "$probe"
    remote_sh <<REMOTE
docker rm -f "$PROJECT-prod-app-new" >/dev/null 2>&1 || true
REMOTE
    die "bản mới KHÔNG khoẻ. Đã gỡ container tạm.
     Production VẪN ĐANG CHẠY BẢN CŨ — không có gì bị đổi, nên không cần rollback.
     Sửa ở máy, test, staging lại. KHÔNG sửa trực tiếp trên production."
  }
  ok "bản mới khoẻ trên cổng tạm ($probe)"
fi

step "11. ĐỔI SANG BẢN MỚI"
docker_promote "$RELEASE_ID" "$PRODUCTION_PORT" "$PROJECT-prod-app" "$PRODUCTION_NETWORK"

step "12. NGHIỆM THU NGAY — HỎNG THÌ TỰ ROLLBACK"
if [ "${DEPLOY_DRY_RUN:-0}" = "1" ]; then
  warn "chạy khô: bỏ qua nghiệm thu"
else
  if "$DEPLOY_DIR/verify.sh" production; then
    ok "nghiệm thu production ĐẠT"
  else
    bad "nghiệm thu production KHÔNG đạt — tự rollback về ${PREV:-bản trước}"
    if [ -n "$PREV" ]; then
      "$DEPLOY_DIR/rollback.sh" production --yes
      die "đã rollback về $PREV. Bản $RELEASE_ID bị loại. Sửa ở máy, không sửa trên production."
    else
      die "KHÔNG rollback được: không có bản trước nào trên máy chủ.
     Đây là lượt triển khai đầu tiên, nên không có đích để quay về."
    fi
  fi
fi

step "KẾT QUẢ"
printf '  URL production : %s\n' "${PRODUCTION_URL:-(chưa có)}"
printf '  RELEASE_ID     : %s\n' "$RELEASE_ID"
printf '  GIT_SHA        : %s\n' "$SHA"
printf '  PREVIOUS       : %s / %s\n' "${PREV:-–}" "${PREV_SHA:-–}"
printf '  BƯỚC TIẾP THEO : git push && git tag (đồng bộ GitHub — xem §7 tài liệu)\n'
