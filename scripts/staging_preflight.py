#!/usr/bin/env python3
"""Kiểm tra trước khi triển khai staging — THOÁT MÃ KHÁC 0 NẾU CHƯA ĐẠT.

VÌ SAO CẦN: mọi thứ trong repo đã xong, nhưng cấu hình sai vẫn làm staging hỏng
theo những cách rất khó lần ra — `PUBLIC_BASE_URL` sai thì **QR in ra trỏ vào
localhost** và chỉ lộ khi đã in; `TRUST_PROXY_HEADERS` sai thì **né được rate
limit**; `ALLOWED_HOSTS` rỗng thì **host-header injection**. Không cái nào báo lỗi
lúc khởi động. Script này biến chúng thành lỗi **ồn ào, trước khi deploy**.

Dùng:
    scripts/staging_preflight.sh                      # đọc biến từ môi trường
    scripts/staging_preflight.sh --env-file .env      # nạp thêm từ file
    scripts/staging_preflight.sh --static-only        # chỉ kiểm cấu hình, không cần DB/mạng

Mã thoát: 0 = tất cả PASS (WARN không chặn) · 1 = có FAIL.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"

#: Giá trị mẫu / chỗ trống — dấu hiệu người dựng staging quên điền.
PLACEHOLDER_PATTERNS = (
    r"<[^>]+>",
    r"\bchangeme\b",
    r"\bchange_me\b",
    r"\byour[-_]",
    r"\bexample\.(com|org|net)\b",
    r"\bxxx+\b",
    r"\bTODO\b",
    r"\bdummy\b",
)

MIN_STAFF_KEY_LEN = 24


@dataclass
class Result:
    name: str
    status: str
    detail: str = ""


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.results.append(Result(name, status, detail))

    @property
    def failures(self) -> list[Result]:
        return [r for r in self.results if r.status == FAIL]

    @property
    def warnings(self) -> list[Result]:
        return [r for r in self.results if r.status == WARN]


def looks_like_placeholder(value: str) -> str | None:
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, value, re.IGNORECASE):
            return pattern
    return None


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


# --------------------------------------------------------------------- STATIC
def check_static(report: Report) -> None:
    app_env = _env("APP_ENV").lower()

    if app_env in {"staging", "production"}:
        report.add("APP_ENV hợp lệ cho staging", PASS, app_env)
    elif app_env in {"dev", "test"}:
        report.add(
            "APP_ENV hợp lệ cho staging",
            FAIL,
            f"APP_ENV={app_env!r} — đây là kiểm tra STAGING, không chạy với dev/test",
        )
    else:
        report.add("APP_ENV hợp lệ cho staging", FAIL, f"APP_ENV={app_env!r} không hợp lệ")

    is_deployed_env = app_env in {"staging", "production"}

    # ---------------------------------------------------------- DATABASE_URL
    db_url = _env("DATABASE_URL")
    if not db_url:
        report.add("DATABASE_URL đã đặt", FAIL, "rỗng")
    else:
        placeholder = looks_like_placeholder(db_url)
        if placeholder:
            report.add("DATABASE_URL không phải giá trị mẫu", FAIL, f"khớp {placeholder!r}")
        else:
            report.add("DATABASE_URL không phải giá trị mẫu", PASS)

        dbname = db_url.rsplit("/", 1)[-1].split("?")[0] or ""

        # THỨ TỰ Ở ĐÂY QUAN TRỌNG — đã từng sai và bị đối chứng âm bắt được.
        # Bản đầu kiểm "tên có chữ staging không" TRƯỚC, nên khi APP_ENV=staging mà
        # tên database là `vipphone_production`, nhánh WARN luôn thắng và phép kiểm
        # production thành MÃ CHẾT: trỏ staging vào database production vẫn exit 0.
        # Nay kiểm "prod" TRƯỚC.
        if re.search(r"prod", dbname, re.IGNORECASE):
            report.add(
                "Database KHÔNG phải production",
                FAIL,
                f"tên database chứa 'prod': {dbname!r} — staging sẽ ghi vào dữ liệu THẬT!",
            )
        elif is_deployed_env and "staging" not in dbname.lower():
            report.add(
                "Database KHÔNG phải production",
                WARN,
                f"tên database là {dbname!r} — xác nhận đây KHÔNG phải database production",
            )
        else:
            report.add("Database KHÔNG phải production", PASS, dbname)

    # -------------------------------------------------------- PUBLIC_BASE_URL
    base = _env("PUBLIC_BASE_URL")
    if not base:
        report.add("PUBLIC_BASE_URL đã đặt", FAIL, "rỗng — QR sẽ không dựng được URL")
    else:
        placeholder = looks_like_placeholder(base)
        if placeholder:
            report.add("PUBLIC_BASE_URL không phải giá trị mẫu", FAIL, f"khớp {placeholder!r}")
        else:
            report.add("PUBLIC_BASE_URL không phải giá trị mẫu", PASS)

        if is_deployed_env and not base.startswith("https://"):
            report.add(
                "PUBLIC_BASE_URL dùng https",
                FAIL,
                f"{base!r} — staging bắt buộc https (QR in ra là địa chỉ này)",
            )
        else:
            report.add("PUBLIC_BASE_URL dùng https", PASS)

        host = re.sub(r"^https?://", "", base).split("/")[0].split(":")[0]
        if is_deployed_env and host in {"localhost", "127.0.0.1", "0.0.0.0"}:
            report.add(
                "PUBLIC_BASE_URL trỏ ra ngoài Internet",
                FAIL,
                f"host={host!r} — khách quét QR sẽ không mở được",
            )
        else:
            report.add("PUBLIC_BASE_URL trỏ ra ngoài Internet", PASS, host)

    # ------------------------------------------------------------ ALLOWED_HOSTS
    allowed = _env("ALLOWED_HOSTS")
    if allowed:
        report.add("ALLOWED_HOSTS đã đặt", PASS, allowed)
        if base:
            host = re.sub(r"^https?://", "", base).split("/")[0].split(":")[0]
            listed = [h.strip() for h in allowed.split(",") if h.strip()]
            if host and host not in listed:
                report.add(
                    "PUBLIC_BASE_URL khớp ALLOWED_HOSTS",
                    FAIL,
                    f"host {host!r} KHÔNG có trong ALLOWED_HOSTS={listed} — mọi request sẽ bị 400",
                )
            else:
                report.add("PUBLIC_BASE_URL khớp ALLOWED_HOSTS", PASS)
    else:
        report.add(
            "ALLOWED_HOSTS đã đặt",
            FAIL,
            "rỗng ⇒ KHÔNG giới hạn Host ⇒ host-header injection",
        )

    # ----------------------------------------------------------- STAFF_API_KEYS
    keys = _env("STAFF_API_KEYS")
    if not keys:
        report.add(
            "STAFF_API_KEYS đã đặt",
            FAIL,
            "rỗng ⇒ toàn bộ khu vực nhân viên trả 503 (fail closed, nhưng staging vô dụng)",
        )
    else:
        placeholder = looks_like_placeholder(keys)
        parsed = [k.strip() for k in keys.split(",") if k.strip()]
        if placeholder:
            report.add("STAFF_API_KEYS không phải giá trị mẫu", FAIL, f"khớp {placeholder!r}")
        elif len(parsed) < 1:
            report.add("STAFF_API_KEYS có ít nhất một khoá", FAIL, "không tách được khoá nào")
        else:
            report.add("STAFF_API_KEYS đã đặt", PASS, f"{len(parsed)} khoá")
            short = [k for k in parsed if len(k) < MIN_STAFF_KEY_LEN]
            if short:
                report.add(
                    "STAFF_API_KEYS đủ mạnh",
                    FAIL,
                    f"có {len(short)} khoá ngắn hơn {MIN_STAFF_KEY_LEN} ký tự — "
                    'sinh bằng: python -c "import secrets; print(secrets.token_urlsafe(32))"',
                )
            else:
                report.add("STAFF_API_KEYS đủ mạnh", PASS)
            if len(parsed) == 1:
                report.add(
                    "STAFF_API_KEYS tách được theo người/quầy",
                    WARN,
                    "chỉ có 1 khoá ⇒ log không phân biệt được ai phát quà",
                )

    # ----------------------------------------------------------------- Turnstile
    site = _env("TURNSTILE_SITE_KEY")
    secret = _env("TURNSTILE_SECRET_KEY")
    required = _env("TURNSTILE_REQUIRED").lower() in {"1", "true", "yes", "on"}

    if required and not (site and secret):
        report.add(
            "Turnstile: cấu hình khớp TURNSTILE_REQUIRED",
            FAIL,
            "TURNSTILE_REQUIRED=true nhưng thiếu khoá site hoặc secret ⇒ CHẶN MỌI LEAD (403)",
        )
    elif required and (site and secret):
        report.add("Turnstile: cấu hình khớp TURNSTILE_REQUIRED", PASS, "đã bật, đủ hai khoá")
    elif site and secret:
        report.add(
            "Turnstile: cấu hình khớp TURNSTILE_REQUIRED",
            WARN,
            "đã có đủ hai khoá nhưng TURNSTILE_REQUIRED=false ⇒ bot protection đang TẮT",
        )
    elif site or secret:
        report.add(
            "Turnstile: cấu hình khớp TURNSTILE_REQUIRED",
            WARN,
            "chỉ có MỘT trong hai khoá ⇒ Turnstile không chạy được (cần cả site và secret)",
        )
    else:
        report.add(
            "Turnstile: cấu hình khớp TURNSTILE_REQUIRED",
            WARN,
            "chưa cấu hình ⇒ bot protection đang TẮT (BLOCKED_EXTERNAL_CREDENTIAL)",
        )

    # ------------------------------------------------------------- minh bạch
    if _env("TRUST_PROXY_HEADERS").lower() in {"1", "true", "yes", "on"}:
        report.add(
            "TRUST_PROXY_HEADERS đã được xác nhận",
            WARN,
            "đang BẬT — chỉ đúng nếu reverse proxy THẬT SỰ ghi đè X-Forwarded-For; "
            "nếu không, client tự đặt header và né được rate limit",
        )

    if _env("EXPOSE_READINESS_DETAILS").lower() in {"1", "true", "yes", "on"}:
        report.add(
            "EXPOSE_READINESS_DETAILS nên tắt",
            WARN,
            "đang BẬT ⇒ /api/ready công khai chi tiết (migration head, cấu hình) cho mọi người",
        )
    else:
        report.add("EXPOSE_READINESS_DETAILS nên tắt", PASS, "false")


# ----------------------------------------------------------------------- LIVE
def check_database(report: Report) -> None:
    db_url = _env("DATABASE_URL")
    if not db_url:
        report.add("Kết nối database", SKIP, "thiếu DATABASE_URL")
        return

    dsn = db_url.replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        import psycopg
    except ImportError:
        report.add("Kết nối database", SKIP, "chưa cài psycopg")
        return

    try:
        with psycopg.connect(dsn, connect_timeout=10) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        report.add("Kết nối database", PASS)
    except Exception as exc:
        report.add("Kết nối database", FAIL, f"{type(exc).__name__}: {exc}")
        return

    # Migration phải ở HEAD — lệch nghĩa là schema không khớp mã đang chạy.
    alembic = shutil.which("alembic") or str(REPO_ROOT / ".venv/bin/alembic")
    if not Path(alembic).exists() and not shutil.which("alembic"):
        report.add("Migration ở HEAD", SKIP, "không tìm thấy alembic")
        return
    try:
        current = subprocess.run(
            [alembic, "current"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
        )
        heads = subprocess.run(
            [alembic, "heads"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
        )
    except Exception as exc:
        report.add("Migration ở HEAD", FAIL, f"không chạy được alembic: {exc}")
        return

    if current.returncode != 0:
        report.add("Migration ở HEAD", FAIL, (current.stderr or current.stdout).strip()[:200])
        return

    cur_ids = re.findall(r"^([0-9a-zA-Z_]+)", current.stdout.strip(), re.M)
    head_ids = re.findall(r"^([0-9a-zA-Z_]+)", heads.stdout.strip(), re.M)
    if not head_ids:
        report.add("Migration ở HEAD", SKIP, "không đọc được head")
    elif cur_ids and cur_ids[0] in head_ids:
        report.add("Migration ở HEAD", PASS, cur_ids[0])
    else:
        report.add(
            "Migration ở HEAD",
            FAIL,
            f"database ở {cur_ids or ['(trống)']} nhưng head là {head_ids} — chạy `alembic upgrade head`",
        )


def _get(url: str, timeout: int = 10) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def check_http(report: Report) -> None:
    base = _env("PUBLIC_BASE_URL")
    if not base:
        report.add("Health check", SKIP, "thiếu PUBLIC_BASE_URL")
        report.add("Readiness check", SKIP, "thiếu PUBLIC_BASE_URL")
        return
    base = base.rstrip("/")

    status, body = _get(f"{base}/api/health")
    if status == 200 and '"ok"' in body:
        report.add("Health check", PASS, f"HTTP {status}")
    else:
        report.add("Health check", FAIL, f"HTTP {status}: {body[:160]}")

    status, body = _get(f"{base}/api/ready")
    if status == 200:
        report.add("Readiness check", PASS, f"HTTP {status}")
    else:
        report.add("Readiness check", FAIL, f"HTTP {status}: {body[:160]}")

    # Chốt an ninh: bản công khai KHÔNG được lộ chi tiết.
    if status == 200 and '"checks"' in body:
        report.add(
            "Readiness KHÔNG lộ chi tiết cho công khai",
            FAIL,
            "response công khai có 'checks' ⇒ đang lộ migration head/cấu hình",
        )
    elif status == 200:
        report.add("Readiness KHÔNG lộ chi tiết cho công khai", PASS)


# ---------------------------------------------------------------------- main
def load_env_file(path: Path) -> int:
    count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra trước khi deploy staging")
    parser.add_argument("--env-file", type=Path, help="nạp thêm biến từ file (không ghi đè env)")
    parser.add_argument("--static-only", action="store_true", help="bỏ qua kiểm tra DB và HTTP")
    args = parser.parse_args()

    if args.env_file:
        if not args.env_file.exists():
            print(f"LỖI: không thấy file {args.env_file}", file=sys.stderr)
            return 1
        n = load_env_file(args.env_file)
        print(f"(đã nạp {n} biến từ {args.env_file})")

    report = Report()
    check_static(report)
    if args.static_only:
        report.add("Kết nối database", SKIP, "--static-only")
        report.add("Migration ở HEAD", SKIP, "--static-only")
        report.add("Health check", SKIP, "--static-only")
        report.add("Readiness check", SKIP, "--static-only")
        report.add("Readiness KHÔNG lộ chi tiết cho công khai", SKIP, "--static-only")
    else:
        check_database(report)
        check_http(report)

    width = max(len(r.name) for r in report.results)
    print("\n" + "=" * (width + 40))
    for r in report.results:
        mark = {PASS: "✓", FAIL: "✗", WARN: "!", SKIP: "-"}[r.status]
        print(f"  {mark} {r.name:<{width}}  {r.status:<4}  {r.detail}")
    print("=" * (width + 40))
    print(
        f"  {len(report.failures)} FAIL · {len(report.warnings)} WARN · "
        f"{len(report.results)} mục đã kiểm"
    )

    if report.failures:
        print("\nCHƯA ĐẠT — sửa các mục FAIL ở trên trước khi deploy.")
        return 1
    print("\nĐẠT — cấu hình đủ điều kiện để deploy staging.")
    if report.warnings:
        print("(có WARN: không chặn, nhưng phải đọc và xác nhận.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
