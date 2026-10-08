#!/usr/bin/env bash
# ============================================================================
# Bộ nghiệm thu staging — chạy được ở LOCAL hoặc trên STAGING.
#
# Cùng một script dùng cho cả hai: truyền --base-url của staging thì nó kiểm
# staging; không truyền thì nó tự dựng server tại máy.
#
# ⚠️  Ghi rõ đang chạy ở đâu: kết quả LOCAL **không** thay thế được STAGING.
# ============================================================================
set -uo pipefail

MODE="${1:-local}"          # local | remote
BASE_URL="${2:-}"
# Python để đọc JSON: venv của CHÍNH repo này, không phải một đường dẫn gán cứng.
# Từng gán cứng $HOME/Projects/vipphone/... ⇒ trên máy khác mọi bước đọc JSON hỏng
# trong im lặng: catalog "0 model", gift code rỗng, redeem bị BLOCKED (#88).
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -z "${PY:-}" ]; then
  if [ -x "$REPO_DIR/.venv/bin/python" ]; then PY="$REPO_DIR/.venv/bin/python"; else PY="$(command -v python3 || true)"; fi
fi
[ -n "$PY" ] && [ -x "$PY" ] || { echo "DỪNG: không tìm thấy python (đặt PY=...)." >&2; exit 2; }
# Khoá nhân viên: nhận cả STAFF_KEY (tên runbook và staging_commerce_smoke.py dùng).
STAFF_API_KEYS="${STAFF_API_KEYS:-${STAFF_KEY:-}}"
PASS=0; FAIL=0; BLOCKED=0; NOTTESTED=0
RESULT_FILE="${RESULT_FILE:-/tmp/staging-acceptance-results.txt}"
: > "$RESULT_FILE"

rec() {  # rec <mục> <PASS|FAIL|BLOCKED|NOT TESTED> <bằng chứng>
  local item="$1" status="$2" ev="${3:-}"
  printf '%-34s %-11s %s\n' "$item" "$status" "$ev" | tee -a "$RESULT_FILE"
  case "$status" in PASS) PASS=$((PASS+1));; FAIL) FAIL=$((FAIL+1));;
    BLOCKED) BLOCKED=$((BLOCKED+1));; *) NOTTESTED=$((NOTTESTED+1));; esac
}

# CHỐT DANH TÍNH: phải chứng minh đang nói chuyện với ĐÚNG ứng dụng VIP PHONE.
# VÌ SAO: lần chạy đầu trúng một `python -m http.server` của phiên khác đang giữ
# cổng, và CẢ 16 mục báo FAIL — tất cả đều là lỗi phép đo, không phải lỗi app.
# Không có chốt này thì một cổng bị chiếm sẽ tạo ra một báo cáo sai hoàn toàn.
HELLO=$(curl -sS -m 10 "$BASE_URL/api/health" 2>/dev/null)
if ! printf '%s' "$HELLO" | grep -q '"service":"vipphone"'; then
  echo "DỪNG: $BASE_URL KHÔNG phải ứng dụng VIP PHONE."
  echo "  nhận được: $(printf '%s' "$HELLO" | head -c 160)"
  echo "  => mọi kết quả bên dưới sẽ vô nghĩa. Kiểm lại cổng/tên miền."
  exit 3
fi

echo "=== BỘ NGHIỆM THU — chế độ: $MODE · $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "DEPLOY_SHA = $(git rev-parse HEAD 2>/dev/null || echo '?')"
echo

# ---------------------------------------------------------------- 1. MIGRATION
echo "--- 1. DATABASE / MIGRATION ---"
if [ "$MODE" = "local" ]; then
  export DATABASE_URL="${DATABASE_URL:?cần DATABASE_URL}"
  BEFORE=$("$PY" -m alembic current 2>&1 | tail -1)
  echo "  alembic current TRƯỚC: ${BEFORE:-<trống>}"
  if "$PY" -m alembic upgrade head >/tmp/acc-mig.log 2>&1; then
    rec "MIGRATION upgrade head" PASS "exit 0"
  else
    rec "MIGRATION upgrade head" FAIL "xem /tmp/acc-mig.log"
  fi
  # PHẢI lọc dòng log TRƯỚC khi tách mã: `alembic` in ra các dòng INFO..., và
  # regex thô sẽ bắt chữ "INFO" làm revision -> báo FAIL giả. Đã dính thật.
  CUR=$("$PY" -m alembic current 2>&1 | grep -vE '^(INFO|WARNING|DEBUG)' | grep -oE '^[0-9a-zA-Z_]+' | head -1)
  HEAD=$("$PY" -m alembic heads 2>&1 | grep -vE '^(INFO|WARNING|DEBUG)' | grep -oE '^[0-9a-zA-Z_]+' | head -1)
  echo "  alembic current SAU: $CUR | heads: $HEAD"
  [ "$CUR" = "$HEAD" ] && rec "MIGRATION ở HEAD" PASS "$CUR" || rec "MIGRATION ở HEAD" FAIL "current=$CUR head=$HEAD"
  if "$PY" -m alembic check >/tmp/acc-check.log 2>&1; then
    rec "MIGRATION alembic check" PASS "không có diff model/migration"
  else
    rec "MIGRATION alembic check" FAIL "$(tail -1 /tmp/acc-check.log)"
  fi
else
  rec "MIGRATION ở HEAD" BLOCKED "cần truy cập database staging"
fi

# ------------------------------------------------------------ 2. HEALTH/READY
echo "--- 2. HEALTH / READINESS ---"
H=$(curl -sS -m 15 -o /tmp/acc-health.json -w '%{http_code}' "$BASE_URL/api/health" 2>/dev/null)
[ "$H" = "200" ] && rec "GET /api/health" PASS "HTTP 200" || rec "GET /api/health" FAIL "HTTP $H"
echo "  body: $(head -c 120 /tmp/acc-health.json)"

R=$(curl -sS -m 15 -o /tmp/acc-ready.json -w '%{http_code}' "$BASE_URL/api/ready" 2>/dev/null)
[ "$R" = "200" ] && rec "GET /api/ready" PASS "HTTP 200" || rec "GET /api/ready" FAIL "HTTP $R"
if grep -q '"checks"' /tmp/acc-ready.json 2>/dev/null; then
  rec "READINESS không lộ chi tiết" FAIL "response công khai có 'checks'"
else
  rec "READINESS không lộ chi tiết" PASS "chỉ có status"
fi

# ---------------------------------------------------------------- 3. LANDING
echo "--- 3. LANDING / STATIC ---"
L=$(curl -sS -m 15 -o /tmp/acc-landing.html -w '%{http_code}' "$BASE_URL/" 2>/dev/null)
[ "$L" = "200" ] && rec "GET / (landing)" PASS "HTTP 200" || rec "GET / (landing)" FAIL "HTTP $L"
grep -qi "<!doctype html" /tmp/acc-landing.html 2>/dev/null && rec "LANDING là HTML" PASS || rec "LANDING là HTML" FAIL
for a in assets/css/styles.css assets/js/app.js assets/js/qr.js; do
  C=$(curl -sS -m 15 -o /dev/null -w '%{http_code}' "$BASE_URL/$a" 2>/dev/null)
  [ "$C" = "200" ] && rec "ASSET $a" PASS "HTTP 200" || rec "ASSET $a" FAIL "HTTP $C"
done
CAT=$(curl -sS -m 15 "$BASE_URL/api/catalog/iphone-models" 2>/dev/null)
N=$(printf '%s' "$CAT" | "$PY" -c 'import json,sys; d=json.load(sys.stdin); d=d.get("models",d) if isinstance(d,dict) else d; print(len(d))' 2>/dev/null || echo 0)
[ "$N" -gt 0 ] 2>/dev/null && rec "CATALOG qua API" PASS "$N model" || rec "CATALOG qua API" FAIL "0 model"

# -------------------------------------------------------- 4. CSP / security hdr
CSP=$(curl -sS -m 15 -D - -o /dev/null "$BASE_URL/" 2>/dev/null | tr -d '\r')
for h in "Content-Security-Policy" "X-Content-Type-Options" "X-Frame-Options" "Referrer-Policy"; do
  echo "$CSP" | grep -qi "^$h:" && rec "HEADER $h" PASS || rec "HEADER $h" FAIL "thiếu"
done

# ------------------------------------------------------------- 5. LEAD FLOW
echo "--- 5. LEAD FLOW (dữ liệu THỬ có marker) ---"
MODEL=$(printf '%s' "$CAT" | "$PY" -c 'import json,sys; d=json.load(sys.stdin); d=d.get("models",d) if isinstance(d,dict) else d; print(d[0]["model_code"])' 2>/dev/null || echo "iphone-16")
PHONE="0900000$(printf '%03d' $((RANDOM % 1000)))"
BODY=$(cat <<JSON
{"full_name":"Staging Acceptance","phone":"$PHONE","iphone_model":"$MODEL","case_color":"Đen",
 "consent":true,"source":"staging-test","utm_campaign":"staging-acceptance"}
JSON
)
LEAD=$(curl -sS -m 20 -X POST "$BASE_URL/api/leads" -H 'Content-Type: application/json' -d "$BODY" -w '\n%{http_code}' 2>/dev/null)
CODE=$(printf '%s' "$LEAD" | tail -1)
JSONBODY=$(printf '%s' "$LEAD" | sed '$d')
if [ "$CODE" = "201" ] || [ "$CODE" = "200" ]; then
  GIFT=$(printf '%s' "$JSONBODY" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("gift_code",""))' 2>/dev/null)
  LEADID=$(printf '%s' "$JSONBODY" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("lead_id",""))' 2>/dev/null)
  rec "POST /api/leads (hợp lệ)" PASS "HTTP $CODE gift=$GIFT"
  echo "$GIFT" > /tmp/acc-gift.txt; echo "$PHONE" > /tmp/acc-phone.txt
else
  rec "POST /api/leads (hợp lệ)" FAIL "HTTP $CODE $(printf '%s' "$JSONBODY" | head -c 150)"
  GIFT=""; PHONE=""
fi

# --------------------------------------------------------------- 6. DUPLICATE
if [ -n "$GIFT" ]; then
  DUP=$(curl -sS -m 20 -X POST "$BASE_URL/api/leads" -H 'Content-Type: application/json' -d "$BODY" -w '\n%{http_code}' 2>/dev/null)
  DCODE=$(printf '%s' "$DUP" | tail -1); DBODY=$(printf '%s' "$DUP" | sed '$d')
  DGIFT=$(printf '%s' "$DBODY" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("gift_code",""))' 2>/dev/null)
  if [ "$DGIFT" = "$GIFT" ]; then rec "DUPLICATE trả CÙNG gift code" PASS "$DGIFT"
  else rec "DUPLICATE trả CÙNG gift code" FAIL "gốc=$GIFT lần2=$DGIFT"; fi
fi

# ---------------------------------------------------------------- 7. QR DECODE
if [ -n "$GIFT" ]; then
  curl -sS -m 20 -o /tmp/acc-qr.png "$BASE_URL/api/gifts/$GIFT/qr.png" 2>/dev/null
  SIZE=$(wc -c < /tmp/acc-qr.png | tr -d ' ')
  if [ "$SIZE" -gt 100 ] 2>/dev/null; then
    rec "GET QR (png)" PASS "$SIZE byte"
    DECODED=$("$PY" - <<'PYEOF' 2>/dev/null
import sys
try:
    import zxingcpp
    from PIL import Image
    r = zxingcpp.read_barcode(Image.open("/tmp/acc-qr.png"))
    print(r.text if r else "")
except Exception:
    print("")
PYEOF
)
    if [ -n "$DECODED" ]; then
      rec "QR DECODE (zxing-cpp, độc lập)" PASS "$DECODED"
      case "$DECODED" in *"$GIFT"*) rec "QR trỏ đúng gift code" PASS;; *) rec "QR trỏ đúng gift code" FAIL "$DECODED";; esac
      case "$DECODED" in *"$PHONE"*) rec "QR KHÔNG chứa PII" FAIL "có số điện thoại";; *) rec "QR KHÔNG chứa PII" PASS;; esac
    else
      rec "QR DECODE (zxing-cpp, độc lập)" FAIL "không giải mã được"
    fi
  else
    rec "GET QR (png)" FAIL "$SIZE byte"
  fi
fi

# ------------------------------------------------------------- 8. STAFF AUTH
echo "--- 8. XÁC THỰC NHÂN VIÊN ---"
U=$(curl -sS -m 15 -o /dev/null -w '%{http_code}' "$BASE_URL/api/gifts/${GIFT:-VIP-26-XXXXXX}" 2>/dev/null)
[ "$U" = "401" ] || [ "$U" = "403" ] || [ "$U" = "503" ] && rec "STAFF không khoá -> từ chối" PASS "HTTP $U" || rec "STAFF không khoá -> từ chối" FAIL "HTTP $U"
I=$(curl -sS -m 15 -o /dev/null -w '%{http_code}' -H "X-Staff-Key: khoa-sai" "$BASE_URL/api/gifts/${GIFT:-VIP-26-XXXXXX}" 2>/dev/null)
[ "$I" = "401" ] && rec "STAFF khoá SAI -> 401" PASS "HTTP $I" || rec "STAFF khoá SAI -> 401" FAIL "HTTP $I"
if [ -n "${STAFF_API_KEYS:-}" ]; then
  K="${STAFF_API_KEYS%%,*}"
  V=$(curl -sS -m 15 -o /tmp/acc-lookup.json -w '%{http_code}' -H "X-Staff-Key: $K" "$BASE_URL/api/gifts/${GIFT:-X}" 2>/dev/null)
  [ "$V" = "200" ] && rec "STAFF khoá ĐÚNG -> 200" PASS || rec "STAFF khoá ĐÚNG -> 200" FAIL "HTTP $V"
  grep -qE 'phone_masked|\*\*\*' /tmp/acc-lookup.json && rec "LOOKUP che số điện thoại" PASS || rec "LOOKUP che số điện thoại" FAIL "không thấy SĐT bị che"
  grep -qE 'utm_source|bni_chapter|company_name' /tmp/acc-lookup.json && rec "LOOKUP không trả PII phụ" FAIL || rec "LOOKUP không trả PII phụ" PASS
else
  rec "STAFF khoá ĐÚNG -> 200" BLOCKED "chưa có STAFF_API_KEYS"
fi
A=$(curl -sS -m 15 -o /dev/null -w '%{http_code}' "$BASE_URL/api/admin/leads" 2>/dev/null)
[ "$A" = "401" ] || [ "$A" = "403" ] || [ "$A" = "503" ] && rec "ADMIN không khoá -> từ chối" PASS "HTTP $A" || rec "ADMIN không khoá -> từ chối" FAIL "HTTP $A"

# ---------------------------------------------------------------- 9. REDEEM
echo "--- 9. REDEEM ---"
if [ -n "${STAFF_API_KEYS:-}" ] && [ -n "$GIFT" ]; then
  K="${STAFF_API_KEYS%%,*}"
  R1=$(curl -sS -m 20 -X POST -H "X-Staff-Key: $K" -H 'Content-Type: application/json' -d '{}' "$BASE_URL/api/gifts/$GIFT/redeem" -w '\n%{http_code}' 2>/dev/null)
  C1=$(printf '%s' "$R1" | tail -1)
  [ "$C1" = "200" ] && rec "REDEEM lần 1" PASS "HTTP 200" || rec "REDEEM lần 1" FAIL "HTTP $C1"
  R2=$(curl -sS -m 20 -X POST -H "X-Staff-Key: $K" -H 'Content-Type: application/json' -d '{}' "$BASE_URL/api/gifts/$GIFT/redeem" -w '\n%{http_code}' 2>/dev/null)
  C2=$(printf '%s' "$R2" | tail -1); B2=$(printf '%s' "$R2" | sed '$d')
  if printf '%s' "$B2" | grep -q '"already_redeemed": *true'; then
    rec "REDEEM lần 2 KHÔNG phát lại" PASS "already_redeemed=true (HTTP $C2)"
  else
    rec "REDEEM lần 2 KHÔNG phát lại" FAIL "HTTP $C2 $(printf '%s' "$B2" | head -c 120)"
  fi
  # Ghi thời điểm phát để chứng minh lần 2 KHÔNG đổi
  A1=$(printf '%s' "$R1" | sed '$d' | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("redeemed_at",""))' 2>/dev/null)
  A2=$(printf '%s' "$B2" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("redeemed_at",""))' 2>/dev/null)
  [ -n "$A1" ] && [ "$A1" = "$A2" ] && rec "REDEEM lần 2 giữ nguyên redeemed_at" PASS "$A1" || rec "REDEEM lần 2 giữ nguyên redeemed_at" FAIL "l1=$A1 l2=$A2"
else
  rec "REDEEM lần 1" BLOCKED "thiếu STAFF_API_KEYS hoặc gift code"
fi

echo
echo "=== TỔNG: PASS=$PASS FAIL=$FAIL BLOCKED=$BLOCKED NOT_TESTED=$NOTTESTED ==="
echo "kết quả chi tiết: $RESULT_FILE"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
