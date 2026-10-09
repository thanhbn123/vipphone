#!/usr/bin/env bash
# =============================================================================
# BỘ THỬ cho bộ triển khai trực tiếp.  Chạy:  bash deploy/tests/thu-deploy.sh
# =============================================================================
# Mỗi cửa khoá được thử HAI chiều:
#   · chiều thuận: điều kiện đủ thì script đi tiếp
#   · chiều NGƯỢC: điều kiện thiếu thì script DỪNG với mã khác 0
# Chỉ thử chiều thuận là cách chắc chắn nhất để có một cửa khoá không khoá gì.
#
# Bộ thử này KHÔNG cần máy chủ, KHÔNG cần Docker, KHÔNG cần mạng.
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="$(dirname "$HERE")"
REPO="$(dirname "$DEPLOY")"

PASS=0; FAIL=0
ok()  { printf '  \033[32mPASS\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }
grp() { printf '\n== %s\n' "$1"; }

# Chạy một đoạn bash có nạp common.sh; trả mã thoát và in ra stdout+stderr.
run_lib() {
  bash -c "
    set +e
    cd '$REPO'
    . '$DEPLOY/common.sh' 2>/dev/null
    $1
  " 2>&1
}
code_of() { run_lib "$1" >/dev/null 2>&1; echo $?; }

grp "1. Cú pháp mọi script"
for f in "$DEPLOY"/*.sh "$HERE"/*.sh; do
  if bash -n "$f" 2>/dev/null; then ok "bash -n $(basename "$f")"; else bad "bash -n $(basename "$f")"; fi
done

grp "2. Mọi script đều fail closed (set -Eeuo pipefail qua common.sh)"
if grep -q 'set -Eeuo pipefail' "$DEPLOY/common.sh"; then
  ok "common.sh đặt set -Eeuo pipefail"
else
  bad "common.sh KHÔNG đặt set -Eeuo pipefail"
fi
for f in staging.sh production.sh rollback.sh backup.sh verify.sh; do
  if grep -q 'common.sh"$' "$DEPLOY/$f" || grep -q 'common\.sh"' "$DEPLOY/$f"; then
    ok "$f nạp common.sh"
  else
    bad "$f KHÔNG nạp common.sh ⇒ không có pipefail, không có bẫy ERR"
  fi
done

grp "3. Dạng mã bản phát hành"
out="$(run_lib 'load_conf; make_release_id 0123456789abcdef')"
if [[ "$out" =~ ^[0-9]{8}-[0-9]{6}-0123456$ ]]; then
  ok "make_release_id → $out"
else
  bad "make_release_id sai dạng: $out"
fi
for good in 20261007-182500-a31df21; do
  [ "$(code_of "valid_release_id $good")" = 0 ] && ok "nhận đúng: $good" || bad "từ chối sai: $good"
done
# Chiều ngược: mọi dạng rác đều phải bị từ chối.
for junk in '20261007-182500-A31DF21' '2026107-182500-a31df21' 'latest' '../../etc/passwd' '20261007-182500-a31df21x' ''; do
  [ "$(code_of "valid_release_id '$junk'")" != 0 ] \
    && ok "từ chối rác: '${junk:-(rỗng)}'" || bad "NHẬN rác: '$junk'"
done

grp "4. Cửa khoá môi trường"
[ "$(code_of 'load_conf; select_env staging')"    = 0 ] && ok "select_env staging đi tiếp"    || bad "select_env staging bị chặn"
[ "$(code_of 'load_conf; select_env production')" = 0 ] && ok "select_env production đi tiếp" || bad "select_env production bị chặn"
for junk in prod stg '' 'staging production' 'staging; rm -rf /'; do
  [ "$(code_of "load_conf; select_env '$junk'")" != 0 ] \
    && ok "từ chối môi trường lạ: '${junk:-(rỗng)}'" || bad "NHẬN môi trường lạ: '$junk'"
done

grp "5. Cửa khoá host (phải DỪNG khi chưa có host/khoá)"
# Ca này phải TỰ DỰNG điều kiện "chưa có host", không được dựa vào việc máy
# trạm chưa có deploy.local.conf. Máy nào đã điền file đó thì ca sẽ tự đạt mà
# chẳng kiểm gì — đã dính đúng thế ở lượt chạy khô đầu tiên.
NOHOST='load_conf; STAGING_HOST=; STAGING_USER=; STAGING_SSH_KEY=; select_env staging; require_host'
out="$(run_lib "$NOHOST")"
if [ "$(code_of "$NOHOST")" != 0 ]; then
  ok "require_host dừng khi chưa có host (điều kiện do chính ca này dựng)"
  case "$out" in
    *deploy.local.conf*) ok "thông báo chỉ đúng chỗ cần điền (deploy.local.conf)" ;;
    *) bad "thông báo không nói phải điền ở đâu: $out" ;;
  esac
else
  bad "require_host ĐI TIẾP dù chưa có host — đây là cửa khoá hỏng"
fi
# Chiều thuận: có host + user + file khoá thật thì đi tiếp.
K="$(mktemp)"; printf 'khoa-gia\n' > "$K"
[ "$(code_of "load_conf; STAGING_HOST=1.2.3.4; STAGING_USER=deploy; STAGING_SSH_KEY=$K; select_env staging; require_host")" = 0 ] \
  && ok "require_host đi tiếp khi đủ host/user/khoá" || bad "require_host chặn dù đã đủ"
# Chiều ngược: khoá trỏ tới file KHÔNG tồn tại.
[ "$(code_of 'load_conf; STAGING_HOST=1.2.3.4; STAGING_USER=deploy; STAGING_SSH_KEY=/khong/co/khoa; select_env staging; require_host')" != 0 ] \
  && ok "require_host dừng khi file khoá không tồn tại" || bad "require_host nhận khoá không tồn tại"
# Chốt SAI HOST — chiều ngược: staging trỏ vào host production (danh sách đã biết,
# hoặc trùng PRODUCTION_HOST) phải DỪNG; production trùng STAGING_HOST phải DỪNG.
for wrong in "160.22.171.228" "9.9.9.9 PRODUCTION_HOST=9.9.9.9"; do
  host="${wrong%% *}"; extra="${wrong#"$host"}"
  out="$(run_lib "load_conf; $extra STAGING_HOST=$host; STAGING_USER=deploy; STAGING_SSH_KEY=$K; select_env staging; require_host")"
  if [ "$(code_of "load_conf; $extra STAGING_HOST=$host; STAGING_USER=deploy; STAGING_SSH_KEY=$K; select_env staging; require_host")" != 0 ] \
     && [[ "$out" == *"SAI HOST"* ]]; then
    ok "staging trỏ vào host production $host ⇒ DỪNG (SAI HOST)"
  else
    bad "staging trỏ vào host production $host mà KHÔNG dừng: $out"
  fi
done
[ "$(code_of "load_conf; STAGING_HOST=1.2.3.4; PRODUCTION_HOST=1.2.3.4; PRODUCTION_USER=deploy; PRODUCTION_SSH_KEY=$K; select_env production; require_host")" != 0 ] \
  && ok "production trùng host staging ⇒ DỪNG" || bad "production trùng host staging mà đi tiếp"
# Chiều thuận: production có host riêng thì đi tiếp.
[ "$(code_of "load_conf; STAGING_HOST=1.2.3.4; PRODUCTION_HOST=5.6.7.8; PRODUCTION_USER=deploy; PRODUCTION_SSH_KEY=$K; select_env production; require_host")" = 0 ] \
  && ok "production host riêng ⇒ đi tiếp" || bad "production host riêng bị chặn"
rm -f "$K"

grp "6. Cửa khoá migration — KHÔNG tự hạ cấp"
[ "$(code_of 'migration_guard upgrade')" = 0 ] && ok "upgrade được phép" || bad "upgrade bị chặn"
[ "$(code_of 'migration_guard downgrade')" != 0 ] && ok "downgrade bị TỪ CHỐI" || bad "downgrade được cho qua — mất dữ liệu là chuyện không rollback được"
[ "$(code_of 'migration_guard bay-gio')" != 0 ] && ok "hướng lạ bị từ chối" || bad "hướng lạ được cho qua"

grp "7. Cửa khoá cây làm việc sạch"
T="$(mktemp -d)"
git -C "$T" init -q 2>/dev/null
git -C "$T" config user.email t@t; git -C "$T" config user.name t
echo a > "$T/a"; git -C "$T" add a; git -C "$T" commit -qm a
mkdir -p "$T/deploy"; cp "$DEPLOY/common.sh" "$DEPLOY/deploy.conf" "$T/deploy/"
# PHẢI commit cả deploy/ — nếu không thì chính nó làm cây bẩn, và ca "cây sạch"
# sẽ hỏng vì lý do không liên quan tới thứ đang thử. (Lỗi phép đo đã gặp thật
# ở lượt chạy đầu: ca này đỏ vì `?? deploy/`.)
git -C "$T" add deploy; git -C "$T" commit -qm deploy
clean_code="$(cd "$T" && bash -c ". deploy/common.sh 2>/dev/null; require_clean_worktree" >/dev/null 2>&1; echo $?)"
[ "$clean_code" = 0 ] && ok "cây sạch thì đi tiếp" || bad "cây sạch vẫn bị chặn (mã $clean_code)"
echo b > "$T/b"
dirty_code="$(cd "$T" && bash -c ". deploy/common.sh 2>/dev/null; require_clean_worktree" >/dev/null 2>&1; echo $?)"
[ "$dirty_code" != 0 ] && ok "cây BẨN thì dừng (kể cả chỉ có file chưa theo dõi)" || bad "cây bẩn vẫn cho triển khai"
dirty_msg="$(cd "$T" && bash -c ". deploy/common.sh 2>/dev/null; require_clean_worktree" 2>&1)"
case "$dirty_msg" in
  *"KHÔNG tự xoá"*) ok "thông báo nói rõ script không xoá/stash gì của người dùng" ;;
  *) bad "thông báo thiếu lời cam kết không xoá dữ liệu người dùng" ;;
esac
rm -rf "$T"

grp "8. production.sh phải DỪNG khi chưa có phiếu staging PASS"
# Chạy trên BẢN SAO SẠCH. Chạy ngay trong repo đang làm việc thì nó dừng ở cửa
# khoá "cây làm việc sạch" và ta đo nhầm cửa khoá — đã dính đúng lỗi này.
C="$(mktemp -d)/repo"
git clone -q --local --no-hardlinks "$REPO" "$C" 2>/dev/null
rm -rf "$C/deploy"; cp -R "$DEPLOY" "$C/deploy"; rm -rf "$C/deploy/state" "$C/deploy/artifacts"
git -C "$C" add -A >/dev/null; git -C "$C" -c user.email=t@t -c user.name=t commit -qm deploy >/dev/null
if [ -n "$(git -C "$C" status --porcelain)" ]; then
  bad "không dựng được bản sao sạch để thử ⇒ ca 8 KHÔNG đo được (không kết luận là đạt)"
fi
out="$(cd "$C" && bash deploy/production.sh 2>&1; echo "mã=$?")"
case "$out" in
  *"mã=0"*) bad "production.sh chạy tới cùng mà KHÔNG có phiếu staging" ;;
  *) ok "production.sh dừng khi chưa có phiếu (hoặc cây chưa sạch)" ;;
esac
case "$out" in
  *"chưa có phiếu staging nào"*|*"phiếu staging PASS nào cho SHA"*)
      ok "dừng ĐÚNG ở cửa khoá phiếu staging (bước 2), không phải ở cửa nào khác" ;;
  *) bad "dừng ở chỗ khác, không phải cửa phiếu staging: $(printf '%s' "$out" | tail -4)" ;;
esac

# 8b. Có phiếu, nhưng của SHA KHÁC ⇒ vẫn phải dừng. Đây là ca quan trọng nhất:
#     một phiếu tồn tại KHÔNG có nghĩa là phiếu cho bản này.
mkdir -p "$C/deploy/state/staging-pass"
cat > "$C/deploy/state/staging-pass/20261007-120000-deadbee.json" <<JSON
{ "release_id": "20261007-120000-deadbee", "git_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef" }
JSON
out="$(cd "$C" && bash deploy/production.sh 2>&1; echo "mã=$?")"
case "$out" in
  *"phiếu staging PASS nào cho SHA"*) ok "có phiếu của SHA KHÁC thì vẫn dừng" ;;
  *"mã=0"*) bad "NHẬN phiếu của SHA khác — cửa khoá vô dụng" ;;
  *) bad "dừng nhưng không phải vì phiếu lệch SHA: $(printf '%s' "$out" | tail -3)" ;;
esac

# 8c. Phiếu ĐÚNG SHA nhưng thiếu sổ artifact ⇒ phải dừng ở bước 3, vì không
#     chứng minh được "cùng một gói đã test ở staging".
REAL_SHA="$(git -C "$C" rev-parse HEAD)"
rm -f "$C/deploy/state/staging-pass"/*.json
cat > "$C/deploy/state/staging-pass/20261007-120000-abcdef0.json" <<JSON
{ "release_id": "20261007-120000-abcdef0", "git_sha": "$REAL_SHA" }
JSON
out="$(cd "$C" && bash deploy/production.sh 2>&1; echo "mã=$?")"
case "$out" in
  *"thiếu sổ artifact"*) ok "có phiếu đúng SHA nhưng thiếu sổ artifact thì vẫn dừng" ;;
  *"mã=0"*) bad "đi tiếp dù không chứng minh được cùng một gói" ;;
  *) bad "dừng vì lý do khác: $(printf '%s' "$out" | tail -3)" ;;
esac
rm -rf "$(dirname "$C")"

grp "8d. state/ và artifacts/ PHẢI được gitignore"
# Nếu không, lượt staging đầu tiên làm cây bẩn và production.sh bị khoá chết.
# Đây là lỗi thật mà bộ thử này đã bắt được lúc viết, không phải ca giả định.
# Đo bằng đường dẫn FILE bên trong: mẫu `state/` chỉ khớp thư mục, và
# `git check-ignore` trên một đường dẫn chưa tồn tại thì không biết nó là thư
# mục nên trả "không khớp" — đúng cái bẫy đã làm ca này đỏ oan lúc viết.
for d in deploy/state/phieu.json deploy/artifacts/goi.tar.gz deploy/deploy.local.conf; do
  if git -C "$REPO" check-ignore -q "$d" 2>/dev/null; then
    ok "$d bị gitignore"
  else
    bad "$d KHÔNG bị gitignore ⇒ deploy xong là cây bẩn, lượt sau bị chặn"
  fi
done

grp "9. Không in secret, không chép secret"
# Chỉ được in TÊN biến. Mọi lệnh in nội dung shared/.env là lỗi.
if grep -nE '(cat|less|head|tail|printf .*|echo .*)[^|]*shared/\.env' "$DEPLOY"/*.sh | grep -v 'grep -c' | grep -v 'grep -oE' | grep -q .; then
  grep -nE '(cat|less|head|tail)[^|]*shared/\.env' "$DEPLOY"/*.sh | sed 's/^/    /'
  bad "có lệnh in nội dung shared/.env"
else
  ok "không script nào in nội dung shared/.env"
fi
if grep -nE 'scp .*\.env|rsync .*\.env' "$DEPLOY"/*.sh | grep -q .; then
  bad "có lệnh chép .env lên/ về máy chủ"
else
  ok "không script nào chép .env đi đâu"
fi
if grep -q 'env-keys.txt' "$DEPLOY/backup.sh" && grep -q "grep -oE '\^\[A-Z_\]+'" "$DEPLOY/backup.sh"; then
  ok "backup.sh chỉ sao lưu TÊN biến, không sao lưu giá trị"
else
  bad "backup.sh không chứng minh được là chỉ lấy tên biến"
fi

grp "10. deploy.conf KHÔNG được chứa host phỏng đoán"
for k in STAGING_HOST PRODUCTION_HOST STAGING_SSH_KEY PRODUCTION_SSH_KEY; do
  v="$(grep -E "^$k=" "$DEPLOY/deploy.conf" | cut -d= -f2-)"
  [ -z "$v" ] && ok "$k để trống trong deploy.conf (đúng: chưa đo thì không điền)" \
               || bad "$k đã có giá trị '$v' trong file vào Git"
done

grp "11. Dockerfile đi đúng đường cài THẬT (chốt cho lỗi STG-1)"
# Bỏ chú thích trước khi đo: Dockerfile có NHẮC tới requirements-dev.txt trong
# phần giải thích vì sao KHÔNG dùng nó. Đo cả chú thích thì phép thử báo sai —
# đã dính đúng thế ở lượt chạy đầu.
DF_CODE="$(grep -vE '^[[:space:]]*#' "$DEPLOY/Dockerfile")"
if printf '%s' "$DF_CODE" | grep -q 'requirements.txt' \
   && ! printf '%s' "$DF_CODE" | grep -q 'requirements-dev'; then
  ok "Dockerfile chỉ cài requirements.txt, KHÔNG cài requirements-dev.txt"
else
  bad "Dockerfile cài dev requirements ⇒ lỗi thiếu phụ thuộc chạy thật lại ẩn được"
fi
if grep -q -- '--workers", "1"' "$DEPLOY/Dockerfile"; then
  ok "uvicorn chạy 1 worker (rate limit giữ trạng thái trong tiến trình)"
else
  bad "không chốt được số worker = 1"
fi

grp "11d. Danh sách check bắt buộc KHÔNG được đòi job đang chạy tay"
# Chốt CHÉO giữa hai file. Ca thật đã xảy ra: job `e2e` chuyển sang
# workflow_dispatch nhưng scripts/enable_branch_protection.sh vẫn đòi ba check
# `E2E (...)` ⇒ branch protection trên develop giữ ba tên đó và PR #64 bị
# BLOCKED. Phép thử này hỏng nếu hai file lệch nhau lần nữa, theo chiều NÀO.
BP="$REPO/scripts/enable_branch_protection.sh"
CI="$REPO/.github/workflows/ci.yml"
if [ -f "$BP" ] && [ -f "$CI" ]; then
  e2e_tay=0
  # KHÔNG dùng dải awk `/^  e2e:/,/^  [a-z0-9-]+:$/`: dòng mở đầu `  e2e:` khớp
  # LUÔN cả mẫu kết thúc, nên dải chỉ gồm đúng một dòng và phép đo ra 0 — đã
  # dính thật lúc viết ca này.
  grep -A 30 '^  e2e:' "$CI" | grep -q "workflow_dispatch'" && e2e_tay=1
  bp_doi=0
  awk '/^CHECKS=\(/,/^\)/' "$BP" | grep -q '"E2E' && bp_doi=1
  if [ "$e2e_tay" = 1 ] && [ "$bp_doi" = 1 ]; then
    bad "ci.yml để e2e chạy TAY nhưng enable_branch_protection.sh VẪN đòi check E2E ⇒ PR sẽ kẹt"
  elif [ "$e2e_tay" = 0 ] && [ "$bp_doi" = 0 ]; then
    bad "e2e chạy trên PR nhưng KHÔNG nằm trong check bắt buộc ⇒ bảo vệ yếu hơn mức đã định"
  else
    ok "ci.yml và enable_branch_protection.sh khớp nhau (e2e tay=$e2e_tay · bp đòi E2E=$bp_doi)"
  fi
  if grep -q 'preflight_checks develop' "$BP"; then
    ok "script bảo vệ nhánh tự đối chiếu danh sách trước khi áp dụng"
  else
    bad "script bảo vệ nhánh KHÔNG đối chiếu ⇒ danh sách viết tay lại lệch trong im lặng"
  fi
fi

grp "12. Chạy khô không được chạm máy chủ"
if grep -q 'DEPLOY_DRY_RUN' "$DEPLOY/common.sh" \
   && awk '/^remote_sh\(\)/,/^}/' "$DEPLOY/common.sh" | grep -q 'DEPLOY_DRY_RUN'; then
  ok "remote_sh tự chặn ở chế độ chạy khô"
else
  bad "remote_sh KHÔNG chặn khi chạy khô ⇒ 'chạy khô' có thể chạm máy chủ thật"
fi

grp "12b. Chạy khô KHÔNG được in PASS cho việc nó chưa làm"
# Lỗi thật đã gặp: lượt chạy khô in "PASS đã đưa bản lên máy chủ" trong khi
# không nối tới máy chủ nào. Dòng PASS sai còn tệ hơn không có dòng nào.
if grep -q 'done_or_dry()' "$DEPLOY/common.sh"; then
  ok "có hàm done_or_dry"
else
  bad "thiếu done_or_dry ⇒ chạy khô có thể in PASS cho việc chưa làm"
fi
for pair in "common.sh:lên máy chủ và kiểm mã băm" "common.sh:đã ghi release.json" \
            "common.sh:đã đổi bản đang chạy sang" "backup.sh:sao lưu \$ENV_NAME xong" \
            "staging.sh:migration ở head" "production.sh:migration ở head"; do
  file="${pair%%:*}"; txt="${pair#*:}"
  if grep -n "$txt" "$DEPLOY/$file" | grep -q '  ok "'; then
    bad "$file: '$txt' vẫn in bằng ok ⇒ chạy khô sẽ nói dối"
  else
    ok "$file: '$txt' đi qua done_or_dry"
  fi
done

grp "13. Phiếu staging chỉ do verify.sh sinh ra"
writers="$(grep -ln 'staging-pass' "$DEPLOY"/*.sh | xargs -n1 basename | sort | tr '\n' ' ')"
case "$writers" in
  *verify.sh*) ok "verify.sh có ghi phiếu" ;;
  *) bad "verify.sh không ghi phiếu" ;;
esac
if grep -ln 'cat > "\$G"' "$DEPLOY"/*.sh | grep -qv verify.sh; then
  bad "có script KHÁC verify.sh cũng ghi phiếu"
else
  ok "chỉ verify.sh ghi nội dung phiếu"
fi

grp "14. Chốt tĩnh cho các lỗi đã gặp trên bản sao staging (#88)"
# mv -f lên symlink current/previous chui VÀO thư mục đích thay vì thay symlink.
if grep -nE 'mv -f .*(current|previous)' "$DEPLOY"/*.sh | grep -qvE '^[^:]+:[0-9]+:[[:space:]]*#'; then
  bad "có 'mv -f' lên symlink current/previous (phải là mv -Tf)"
else
  ok "mọi lần thay symlink current/previous đều dùng mv -Tf"
fi
# Gọi ứng dụng qua 127.0.0.1 mà không gửi Host ⇒ 400 Invalid host header.
nohost="$(grep -nE 'curl .*127\.0\.0\.1' "$DEPLOY"/*.sh | grep -v host_header || true)"
[ -z "$nohost" ] && ok "mọi curl vào 127.0.0.1 đều gửi Host (host_header)" || bad "curl vào 127.0.0.1 thiếu Host: $nohost"
# Cổng tạm "cổng chính + 1" đã đụng cổng của dự án khác.
if grep -nE '(PORT|port) \+ 1' "$DEPLOY"/*.sh >/dev/null; then
  bad "còn cổng tạm kiểu 'cổng chính + 1'"
else
  ok "cổng tạm lấy từ *_TEMP_PORT, không phải cổng chính + 1"
fi
[ "$(code_of 'load_conf; select_env staging; [ -n "$ENV_TEMP_PORT" ] && [ "$ENV_TEMP_PORT" != "$STAGING_PORT" ]')" = 0 ] \
  && ok "STAGING_TEMP_PORT có giá trị và khác cổng chính" || bad "STAGING_TEMP_PORT thiếu hoặc trùng cổng chính"
[ "$(code_of 'load_conf; select_env staging; ENV_URL=https://qua.viporder.vn/x; [ "$(host_header)" = "-H '"'"'Host: qua.viporder.vn'"'"'" ]')" = 0 ] \
  && ok "host_header lấy đúng tên máy từ URL" || bad "host_header sai"

grp "15. Heredoc trong \$( ) phải sống được với bash 3.2 của macOS (#92)"
# bash 3.2 đếm ngoặc CẢ trong thân heredoc nằm trong $( ): một dấu `)` lẻ (mẫu
# `case`) cắt `$(` sớm ⇒ máy chủ nhận script cụt, phần còn lại chạy tại máy trạm.
# (a) quét tĩnh: mọi heredoc `$(remote_... <<TAG` phải cân ngoặc.
lech="$(python3 - "$DEPLOY" <<'PY'
import re, sys, glob
for f in sorted(glob.glob(sys.argv[1] + "/*.sh")):
    lines = open(f, encoding="utf-8").read().split("\n")
    i = 0
    while i < len(lines):
        m = re.search(r"\$\(\s*remote_\w+\s*<<-?\s*['\"]?(\w+)", lines[i])
        if m:
            tag, start, body = m.group(1), i + 1, []
            i += 1
            while i < len(lines) and lines[i].strip() != tag:
                body.append(lines[i]); i += 1
            txt = "\n".join(body)
            if txt.count("(") != txt.count(")"):
                print(f"{f}:{start} mở={txt.count('(')} đóng={txt.count(')')}")
        i += 1
PY
)"
[ -z "$lech" ] && ok "24 heredoc \$(remote_* <<TAG) đều cân ngoặc" || bad "heredoc lệch ngoặc (bash 3.2 sẽ cắt): $lech"
# (b) chạy thật require_ports dưới /bin/bash của máy với remote_capture giả: script
#     gửi đi phải nguyên vẹn (có nhánh "OK trong" ở cuối) và không chạy gì tại máy trạm.
cap="$(mktemp)"
out="$(/bin/bash -c "
  cd '$REPO'; . '$DEPLOY/common.sh' 2>/dev/null
  remote_capture() { cat > '$cap'; echo 'OK trong'; }
  ENV_NAME=staging ENV_UPPER=STAGING
  require_ports 18080 18180 vipphone-staging-app
" 2>&1)"; rc=$?
if [ "$rc" = 0 ] && grep -q 'echo "OK trong"' "$cap" && [ "$(tail -1 "$cap")" = "fi" ]; then
  ok "require_ports gửi heredoc nguyên vẹn dưới $(/bin/bash -c 'echo bash $BASH_VERSION')"
else
  bad "require_ports hỏng dưới /bin/bash (mã $rc): $(printf '%s' "$out" | tail -2 | tr '\n' ' ')"
fi
# (c) logic ở xa: chạy phần thân (bỏ 2 dòng định nghĩa) với listening/owner giả.
body="$(sed 1,2d "$cap")"
ports_case() { # <muốn> <chính nghe?> <tạm nghe?> <chủ cổng>
  local want="$1" L="$2" T="$3" O="$4" got
  got="$(bash -c "listening(){ [ \"\$1\" = 18180 ] && [ '$T' = 1 ] && return 0; [ \"\$1\" = 18080 ] && [ '$L' = 1 ] && return 0; return 1; }; owner(){ echo '$O'; }; $body" 2>&1)"
  [ "$got" = "$want" ] && ok "cổng: $want" || bad "cổng: muốn [$want] được [$got]"
}
ports_case "OK vipphone-staging-app"          1 0 vipphone-staging-app
ports_case "OK vipphone-staging-app-prev-123" 1 0 vipphone-staging-app-prev-123
ports_case "CHINH_BAN viporder-nginx-1"       1 0 viporder-nginx-1
ports_case "OK trong"                         0 0 ""
ports_case "TAM_BAN viporder-nginx-1"         0 1 viporder-nginx-1
rm -f "$cap"
# (d) đối chứng âm: một heredoc có `)` lẻ PHẢI bị bash 3.2 làm hỏng — chứng minh ca (b)
#     đo đúng thứ cần đo. Trên bash ≥ 4 không có lỗi này: ghi rõ ca (b) chỉ là chiều thuận.
neg="$(/bin/bash -c '
  cap() { cat; }
  f() { out="$(cap <<R
case "x" in
  *) echo "a" ;;
esac
R
)"; printf "%s" "$out"; }
  f' 2>&1)"
want="$(printf 'case "x" in\n  *) echo "a" ;;\nesac')"
bmaj="$(/bin/bash -c 'echo ${BASH_VERSINFO[0]}')"
if [ "$neg" != "$want" ]; then
  ok "đối chứng âm: /bin/bash $bmaj.x làm hỏng heredoc có ) lẻ đúng như #92 ⇒ ca (b) có giá trị"
elif [ "$bmaj" -ge 4 ]; then
  ok "đối chứng âm: /bin/bash $bmaj.x không có lỗi #92 — ca (b) ở máy này chỉ là chiều thuận"
else
  bad "đối chứng âm: /bin/bash $bmaj.x KHÔNG làm hỏng heredoc có ) lẻ — không hiểu, xem lại"
fi

grp "16. scp phải nhận đường dẫn TUYỆT ĐỐI (OpenSSH ≥ 9 chạy SFTP, không nở \$HOME) (#95)"
# ship_release với remote_* và scp giả: đích scp không được chứa `$`, phải là đường
# dẫn máy chủ đã nở; và không được scp khi máy chủ không trả về đường dẫn tuyệt đối.
ship_out="$(/bin/bash -c "
  cd '$REPO'; . '$DEPLOY/common.sh' 2>/dev/null
  ENV_NAME=staging ENV_ROOT='\$HOME/vip/vipphone/staging' ENV_USER=deploy ENV_HOST=h ENV_KEY=/dev/null
  ARTIFACT=/tmp/x.tar.gz ARTIFACT_SHA256=0
  remote_sh() { cat >/dev/null; }
  remote_capture() { cat >/dev/null; echo /home/deploy/vip/vipphone/staging; }
  scp() { echo \"SCP_DEST=\${@: -1}\"; }
  ship_release r1
" 2>&1)"
dest="$(printf '%s\n' "$ship_out" | sed -n 's/^SCP_DEST=//p')"
case "$dest" in
  'deploy@h:/home/deploy/vip/vipphone/staging/incoming/') ok "scp tới đường dẫn tuyệt đối do máy chủ nở: $dest" ;;
  *'$'*) bad "scp vẫn mang nguyên chữ \$ (SFTP sẽ hỏng): ${dest:-<không scp>}" ;;
  *) bad "đích scp lạ: ${dest:-<không scp>} · $(printf '%s' "$ship_out" | tail -1)" ;;
esac
ship_bad="$(/bin/bash -c "
  cd '$REPO'; . '$DEPLOY/common.sh' 2>/dev/null
  ENV_NAME=staging ENV_ROOT='\$HOME/vip/vipphone/staging' ENV_USER=deploy ENV_HOST=h ENV_KEY=/dev/null
  ARTIFACT=/tmp/x.tar.gz ARTIFACT_SHA256=0
  remote_sh() { cat >/dev/null; }
  remote_capture() { cat >/dev/null; echo; }
  scp() { echo SCP_DA_CHAY; }
  ship_release r1
" 2>&1)"; rc=$?
if [ "$rc" != 0 ] && ! printf '%s' "$ship_bad" | grep -q SCP_DA_CHAY; then
  ok "máy chủ không trả đường dẫn tuyệt đối ⇒ DỪNG trước scp (mã $rc)"
else
  bad "máy chủ trả rỗng mà vẫn scp hoặc không dừng (mã $rc)"
fi

printf '\n== KẾT QUẢ: %d đạt · %d không đạt\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
