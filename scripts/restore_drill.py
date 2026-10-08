#!/usr/bin/env python3
"""Diễn tập SAO LƯU → PHỤC HỒI, có kiểm nội dung. Xem `docs/backup-restore.md`.

Không có bản sao lưu nào đã được kiểm thì chưa có bản sao lưu nào. Script này:

  1. `pg_dump -Fc` database nguồn ra tệp tạm (kèm sha256, kích thước, thời gian).
  2. Tạo database MỚI `<nguồn>_restore_drill_<thời điểm>` — KHÔNG BAO GIỜ đè lên
     database đang chạy (từ chối nếu tên đã tồn tại).
  3. `pg_restore --no-owner --no-privileges` vào database mới.
  4. So nguồn ↔ bản phục hồi: migration head, danh sách bảng, SỐ DÒNG và MD5 NỘI
     DUNG (sắp theo khoá chính) của từng bảng. Số dòng khớp mà nội dung lệch vẫn
     là phục hồi hỏng — nên phải so md5.
  5. Xoá database tạm (trừ khi `--keep`) và tệp dump tạm (chứa PII).

Hai cách chạy:

- Tại máy (có psycopg + pg_dump):
    scripts/restore_drill.py --database-url "$DATABASE_URL"
- TRÊN MÁY CHỦ STAGING, nơi chỉ container PostgreSQL có `pg_dump` (image ứng dụng
  là python-slim, không có). Chỉ cần `python3` hệ thống, không cần thư viện nào:
    python3 scripts/restore_drill.py --docker-pg vipphone-staging-pg \\
        --db vipphone_staging --user vipphone

Chỉ ĐỌC database nguồn.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

#: Bảng phải có mặt và khớp nội dung — đúng các bảng mà mất là mất tiền/khách.
CRITICAL_TABLES = (
    "leads",
    "customers",
    "customer_acquisition",
    "orders",
    "order_items",
    "payments",
    "payment_events",
    "inventory_balances",
    "inventory_movements",
    "price_history",
    "product_variants",
    "products",
)

SEP = "\x1f"


def dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def with_db(url: str, name: str) -> str:
    parts = urlsplit(dsn(url))
    return urlunsplit(parts._replace(path="/" + name))


# --------------------------------------------------------------------------
# Backend: cách nói chuyện với PostgreSQL
# --------------------------------------------------------------------------
class PsycopgBackend:
    """Tại máy: psycopg cho truy vấn, pg_dump/pg_restore của máy."""

    def __init__(self, url: str) -> None:
        self.url = dsn(url)
        self.source = urlsplit(self.url).path.lstrip("/")

    def query(self, db: str, sql: str) -> list[tuple[str, ...]]:
        import psycopg

        with psycopg.connect(with_db(self.url, db)) as conn:
            rows = conn.execute(sql).fetchall()
        return [tuple("" if v is None else str(v) for v in row) for row in rows]

    def admin(self, sql: str) -> list[tuple[str, ...]]:
        import psycopg

        with psycopg.connect(with_db(self.url, "postgres"), autocommit=True) as conn:
            cur = conn.execute(sql)
            return [tuple(str(v) for v in r) for r in cur.fetchall()] if cur.description else []

    def dump(self, path: str) -> None:
        subprocess.run(["pg_dump", "-Fc", "-d", self.url, "-f", path], check=True)

    def restore(self, target: str, path: str) -> None:
        subprocess.run(
            [
                "pg_restore",
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                "-d",
                with_db(self.url, target),
                path,
            ],
            check=True,
        )


class DockerPgBackend:
    """Trên máy chủ: mọi thứ chạy TRONG container PostgreSQL qua `docker exec`.

    Mật khẩu không đi qua dòng lệnh: dùng xác thực local socket của chính container.
    """

    def __init__(self, container: str, db: str, user: str) -> None:
        self.container, self.source, self.user = container, db, user

    def _exec(self, *args: str, stdin: bytes | None = None) -> bytes:
        return subprocess.run(
            ["docker", "exec", "-i", self.container, *args],
            input=stdin,
            check=True,
            capture_output=True,
        ).stdout

    def query(self, db: str, sql: str) -> list[tuple[str, ...]]:
        out = self._exec(
            "psql", "-U", self.user, "-d", db, "-At", "-F", SEP, "-v", "ON_ERROR_STOP=1", "-c", sql
        ).decode()
        return [tuple(line.split(SEP)) for line in out.splitlines() if line]

    def admin(self, sql: str) -> list[tuple[str, ...]]:
        return self.query("postgres", sql)

    def dump(self, path: str) -> None:
        data = self._exec("pg_dump", "-U", self.user, "-d", self.source, "-Fc")
        with open(path, "wb") as handle:
            handle.write(data)

    def restore(self, target: str, path: str) -> None:
        with open(path, "rb") as handle:
            self._exec(
                "pg_restore",
                "-U",
                self.user,
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                "-d",
                target,
                stdin=handle.read(),
            )


# --------------------------------------------------------------------------
def snapshot(backend, db: str) -> dict:
    head = [r[0] for r in backend.query(db, "SELECT version_num FROM alembic_version")]
    tables = [
        r[0]
        for r in backend.query(
            db,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1",
        )
    ]
    content: dict[str, tuple[int, str]] = {}
    for table in tables:
        pk = [
            r[0]
            for r in backend.query(
                db,
                "SELECT a.attname FROM pg_index i JOIN pg_attribute a "
                "ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                f"WHERE i.indrelid = '\"{table}\"'::regclass AND i.indisprimary",
            )
        ]
        order = ", ".join(f'"{c}"' for c in pk) if pk else "1"
        ((count, digest),) = backend.query(
            db,
            f"SELECT count(*), md5(coalesce(string_agg(t::text, E'\\n' ORDER BY {order}), '')) "
            f'FROM "{table}" t',
        )
        content[table] = (int(count), digest)
    return {"head": head, "tables": tables, "content": content}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diễn tập sao lưu → phục hồi có kiểm nội dung")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--docker-pg", help="tên container PostgreSQL (chế độ máy chủ)")
    parser.add_argument("--db", help="tên database nguồn (chế độ --docker-pg)")
    parser.add_argument("--user", default="vipphone", help="user PostgreSQL (chế độ --docker-pg)")
    parser.add_argument("--keep", action="store_true", help="giữ database phục hồi để soi tay")
    args = parser.parse_args(argv)

    if args.docker_pg:
        if not args.db:
            print("LỖI: --docker-pg cần --db.", file=sys.stderr)
            return 2
        backend = DockerPgBackend(args.docker_pg, args.db, args.user)
    elif args.database_url:
        backend = PsycopgBackend(args.database_url)
    else:
        print("LỖI: cần --database-url hoặc --docker-pg.", file=sys.stderr)
        return 2

    source = backend.source
    if "prod" in source.lower():
        print(f"TỪ CHỐI: database nguồn {source!r} có chữ 'prod'.", file=sys.stderr)
        return 2
    target = f"{source}_restore_drill_{datetime.now(UTC):%Y%m%d%H%M%S}"
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="vipphone-drill-") as tmp:
        dump_path = os.path.join(tmp, "drill.dump")
        print(f"1. pg_dump -Fc {source}")
        started = time.monotonic()
        backend.dump(dump_path)
        with open(dump_path, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        print(
            f"   dump {os.path.getsize(dump_path)} byte · {time.monotonic() - started:.1f}s · "
            f"sha256 {digest[:16]}…"
        )

        if backend.admin(f"SELECT 1 FROM pg_database WHERE datname = '{target}'"):
            print(f"TỪ CHỐI: database {target} đã tồn tại.", file=sys.stderr)
            return 2
        backend.admin(f'CREATE DATABASE "{target}"')
        print(f"2. tạo database MỚI {target}")

        try:
            print("3. pg_restore --no-owner --no-privileges")
            started = time.monotonic()
            backend.restore(target, dump_path)
            print(f"   phục hồi xong trong {time.monotonic() - started:.1f}s")
            a, b = snapshot(backend, source), snapshot(backend, target)

            print("4. so nguồn ↔ bản phục hồi")
            print(f"   migration head : {a['head']} ↔ {b['head']}")
            if a["head"] != b["head"]:
                failures.append("migration head lệch")
            print(f"   số bảng        : {len(a['tables'])} ↔ {len(b['tables'])}")
            if a["tables"] != b["tables"]:
                failures.append("danh sách bảng lệch")
            for table in CRITICAL_TABLES:
                if table not in a["content"]:
                    failures.append(f"thiếu bảng quan trọng {table}")
                    continue
                left, right = a["content"][table], b["content"].get(table)
                mark = "OK " if left == right else "LỆCH"
                print(f"   [{mark}] {table:<22} {left[0]:>6} dòng  md5 {left[1][:12]}")
                if left != right:
                    failures.append(f"{table} lệch")
            mismatched = [t for t in a["tables"] if a["content"][t] != b["content"].get(t)]
            print(f"   bảng khớp md5   : {len(a['tables']) - len(mismatched)}/{len(a['tables'])}")
            failures += [f"{t} lệch" for t in mismatched if t not in CRITICAL_TABLES]
        finally:
            if not args.keep:
                backend.admin(f'DROP DATABASE IF EXISTS "{target}"')
                print(f"5. đã xoá database tạm {target}; tệp dump tạm đã xoá")

    if failures:
        print("KẾT QUẢ: FAIL — " + "; ".join(failures), file=sys.stderr)
        return 1
    print("KẾT QUẢ: PASS — bản phục hồi khớp nguồn (head, bảng, số dòng, md5 nội dung).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
