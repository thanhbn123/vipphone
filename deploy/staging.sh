#!/usr/bin/env bash
# =============================================================================
# TRIỂN KHAI STAGING — VIP PHONE
#   ./deploy/staging.sh                 triển khai thật
#   DEPLOY_DRY_RUN=1 ./deploy/staging.sh   in kế hoạch, không chạm máy chủ
# =============================================================================
# GitHub Actions KHÔNG phải điều kiện của bước này. Nhưng test tại máy thì CÓ:
# không có lượt nào đi lên staging mà chưa qua test.
# =============================================================================
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
load_conf
select_env staging

SHA=""; RELEASE_ID=""

step "1. KIỂM TRA REPO TẠI MÁY"
require_clean_worktree
SHA="$(git_sha)"
BRANCH="$(git_branch)"
TREE="$(git_tree_sha)"
RELEASE_ID="$(make_release_id "$SHA")"
valid_release_id "$RELEASE_ID" || die "release id sai dạng: $RELEASE_ID"
ok "nhánh $BRANCH · SHA $SHA"
ok "release id $RELEASE_ID"

step "2. CHẠY TEST TẠI MÁY"
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PY="$REPO_ROOT/.venv/bin/python"
elif [ -n "${DEPLOY_PYTHON:-}" ] && [ -x "$DEPLOY_PYTHON" ]; then
  PY="$DEPLOY_PYTHON"
else
  die "không thấy $REPO_ROOT/.venv/bin/python.
     Tạo venv (make venv && make install-dev) hoặc chỉ đường bằng DEPLOY_PYTHON=...
     Script KHÔNG bỏ qua bước test — bỏ test là bỏ đúng thứ bước này tồn tại để làm."
fi
ok "python: $PY ($("$PY" -V 2>&1))"
for raw in "${LOCAL_TEST_CMDS[@]}"; do
  cmd="${raw//\$PY/$PY}"
  log "→ $cmd"
  if ! ( cd "$REPO_ROOT" && eval "$cmd" ); then
    [ -n "${TEST_DATABASE_URL:-}" ] || warn "TEST_DATABASE_URL chưa đặt — bộ test cần PostgreSQL sống (xem docs/DIRECT-DEPLOY.md §2)"
    die "test tại máy KHÔNG đạt: $cmd"
  fi
  ok "$cmd"
done

step "3. ĐÓNG GÓI ARTIFACT"
require_host
build_artifact "$RELEASE_ID" "$DEPLOY_DIR/artifacts"

# Ghi lại mã băm artifact ở máy trạm. production.sh sẽ dựng lại gói từ đúng
# SHA này và đòi mã băm trùng khớp — đó là cách "promotion cùng một artifact"
# được CHỨNG MINH chứ không chỉ được nói.
mkdir -p "$STATE_DIR/artifacts"
cat > "$STATE_DIR/artifacts/$RELEASE_ID.json" <<JSON
{
  "release_id": "$RELEASE_ID",
  "git_sha": "$SHA",
  "artifact_sha256": "$ARTIFACT_SHA256",
  "built_at": "$(_ts)"
}
JSON
ok "đã ghi sổ artifact: $STATE_DIR/artifacts/$RELEASE_ID.json"

step "4. ĐƯA BẢN PHÁT HÀNH LÊN STAGING"
require_shared_env
ship_release "$RELEASE_ID"

step "5. SAO LƯU TRƯỚC KHI ĐỔI"
# Staging cũng sao lưu: một lượt migration sai ở staging mà mất dữ liệu thử thì
# lần nghiệm thu sau phải dựng lại từ đầu.
"$DEPLOY_DIR/backup.sh" staging

step "6. MIGRATION"
migration_guard upgrade
remote_sh <<REMOTE
ROOT="$ENV_ROOT"
IMG_BASE="python:3.12-slim"
# Migration chạy bằng chính ảnh của bản phát hành, để alembic và mã nguồn luôn
# cùng một phiên bản. Ảnh được build ở bước sau, nên ở đây build trước.
docker build -q -t "$PROJECT-$ENV_NAME:$RELEASE_ID" \
  -f "\$ROOT/releases/$RELEASE_ID/deploy/Dockerfile" "\$ROOT/releases/$RELEASE_ID" >/dev/null
docker run --rm --network "$STAGING_NETWORK" --env-file "\$ROOT/shared/.env" \
  "$PROJECT-$ENV_NAME:$RELEASE_ID" alembic upgrade head
docker run --rm --network "$STAGING_NETWORK" --env-file "\$ROOT/shared/.env" \
  "$PROJECT-$ENV_NAME:$RELEASE_ID" alembic check
echo "alembic upgrade + check xong"
REMOTE
done_or_dry "migration ở head và alembic check sạch"

step "7. CHẠY BẢN MỚI (tên tạm, cổng tạm)"
docker_run_release "$RELEASE_ID" "$STAGING_PORT" "$PROJECT-staging-app" "$STAGING_NETWORK" "$STAGING_PG_CONTAINER"

step "8. HEALTH CHECK BẢN MỚI TRƯỚC KHI ĐỔI"
if [ "${DEPLOY_DRY_RUN:-0}" = "1" ]; then
  warn "chạy khô: không gọi được health"
else
  probe="$(remote_capture <<REMOTE
for i in \$(seq 1 30); do
  code=\$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://127.0.0.1:$((STAGING_PORT + 1))$HEALTH_PATH" || echo 000)
  if [ "\$code" = "200" ]; then echo "OK \$i"; exit 0; fi
  sleep 2
done
echo "FAIL \$code"
docker logs --tail 40 "$PROJECT-staging-app-new" 2>&1 | sed 's/^/    log| /'
exit 1
REMOTE
)" || {
    printf '%s\n' "$probe"
    remote_sh <<REMOTE
docker rm -f "$PROJECT-staging-app-new" >/dev/null 2>&1 || true
REMOTE
    die "bản mới KHÔNG khoẻ — đã gỡ container tạm, bản đang chạy KHÔNG bị đụng tới"
  }
  ok "health 200 trên cổng tạm ($probe)"
fi

step "9. ĐỔI SANG BẢN MỚI"
docker_promote "$RELEASE_ID" "$STAGING_PORT" "$PROJECT-staging-app" "$STAGING_NETWORK"

step "10. ĐỐI CHIẾU MÃ TRÊN MÁY CHỦ VỚI CÂY ĐÃ COMMIT"
if [ "${DEPLOY_DRY_RUN:-0}" = "1" ]; then
  warn "chạy khô: không đo được băm cây trên máy chủ"
else
  rsha="$(remote_tree_sha "$RELEASE_ID")"
  [ -n "$rsha" ] || die "không đo được băm cây trên máy chủ — KHÔNG kết luận là khớp"
  ok "băm cây trên máy chủ: $rsha"
  ok "git tree sha (máy trạm): $TREE"
  log "hai con số trên là HAI phép đo KHÁC NHAU (git object vs sha256 nội dung file)"
  log "nên chúng KHÔNG so trực tiếp được; verify.sh so bằng cùng một phép đo."
fi

step "11. GHI METADATA"
write_release_json "$RELEASE_ID" "$SHA" "$BRANCH" "$TREE"
remote_prune

step "12. KẾT QUẢ"
printf '  URL staging    : %s\n' "${STAGING_URL:-(chưa có)}"
printf '  RELEASE_ID     : %s\n' "$RELEASE_ID"
printf '  GIT_SHA        : %s\n' "$SHA"
printf '  BƯỚC TIẾP THEO : ./deploy/verify.sh staging\n'
printf '\n  %sStaging đã triển khai, NHƯNG CHƯA nghiệm thu.%s\n' "$C_WARN" "$C_0"
printf '  Chỉ `verify.sh staging` mới sinh ra phiếu cho phép production chạy.\n'
