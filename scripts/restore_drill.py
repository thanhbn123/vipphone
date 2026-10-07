#!/usr/bin/env python3
"""Diễn tập SAO LƯU → PHỤC HỒI, có kiểm nội dung. Xem `docs/backup-restore.md`.

Không có bản sao lưu nào đã được kiểm thì chưa có bản sao lưu nào. Script này:

  1. `pg_dump -Fc` database nguồn ra tệp tạm (kèm sha256).
  2. Tạo database MỚI `<nguồn>_restore_drill_<thời điểm>` — KHÔNG BAO GIỜ đè lên
     database đang chạy (từ chối nếu tên đã tồn tại).
  3. `pg_restore --no-owner --no-privileges` vào database mới.
  4. So nguồn ↔ bản phục hồi: migration head, danh sách bảng, SỐ DÒNG và MD5 NỘI
     DUNG (sắp theo khoá chính) của từng bảng. Số dòng khớp mà nội dung lệch vẫn
     là phục hồi hỏng — nên phải so md5.
  5. Xoá database tạm (trừ khi `--keep`). Tệp dump tạm luôn bị xoá: nó chứa PII.

Chỉ ĐỌC database nguồn. Không cần quyền gì ngoài CREATE DATABASE trên máy chủ PG.

Dùng:
    scripts/restore_drill.py --database-url "$DATABASE_URL"
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
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


def dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def with_db(url: str, name: str) -> str:
    parts = urlsplit(dsn(url))
    return urlunsplit(parts._replace(path="/" + name))


def snapshot(conn) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT version_num FROM alembic_version")
    head = [r[0] for r in cur.fetchall()]
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1"
    )
    tables = [r[0] for r in cur.fetchall()]
    content: dict[str, tuple[int, str]] = {}
    for table in tables:
        cur.execute(
            "SELECT a.attname FROM pg_index i JOIN pg_attribute a "
            "ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = %s::regclass AND i.indisprimary",
            (table,),
        )
        pk = [r[0] for r in cur.fetchall()] or ["1"]
        order = ", ".join(f'"{c}"' if c != "1" else c for c in pk)
        cur.execute(
            f"SELECT count(*), md5(coalesce(string_agg(t::text, E'\\n' ORDER BY {order}), '')) "
            f'FROM "{table}" t'
        )
        count, digest = cur.fetchone()
        content[table] = (int(count), digest)
    return {"head": head, "tables": tables, "content": content}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diễn tập sao lưu → phục hồi có kiểm nội dung")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--keep", action="store_true", help="giữ database phục hồi để soi tay")
    args = parser.parse_args(argv)
    if not args.database_url:
        print("LỖI: thiếu --database-url / DATABASE_URL.", file=sys.stderr)
        return 2

    import psycopg

    source_url = dsn(args.database_url)
    source_name = urlsplit(source_url).path.lstrip("/")
    target_name = f"{source_name}_restore_drill_{datetime.now(UTC):%Y%m%d%H%M%S}"
    admin_url = with_db(source_url, "postgres")

    with tempfile.TemporaryDirectory(prefix="vipphone-drill-") as tmp:
        dump_path = os.path.join(tmp, "drill.dump")
        print(f"1. pg_dump -Fc {source_name}")
        subprocess.run(["pg_dump", "-Fc", "-d", source_url, "-f", dump_path], check=True)
        with open(dump_path, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        print(f"   dump {os.path.getsize(dump_path)} byte · sha256 {digest[:16]}…")

        with psycopg.connect(admin_url, autocommit=True) as admin:
            exists = admin.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (target_name,)
            ).fetchone()
            if exists:
                print(f"TỪ CHỐI: database {target_name} đã tồn tại.", file=sys.stderr)
                return 2
            admin.execute(f'CREATE DATABASE "{target_name}"')
        print(f"2. tạo database MỚI {target_name}")

        try:
            print("3. pg_restore --no-owner --no-privileges")
            subprocess.run(
                [
                    "pg_restore",
                    "--no-owner",
                    "--no-privileges",
                    "--exit-on-error",
                    "-d",
                    with_db(source_url, target_name),
                    dump_path,
                ],
                check=True,
            )
            with (
                psycopg.connect(source_url) as src,
                psycopg.connect(with_db(source_url, target_name)) as dst,
            ):
                a, b = snapshot(src), snapshot(dst)

            print("4. so nguồn ↔ bản phục hồi")
            failures = []
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
                with psycopg.connect(admin_url, autocommit=True) as admin:
                    admin.execute(f'DROP DATABASE IF EXISTS "{target_name}"')
                print(f"5. đã xoá database tạm {target_name}; tệp dump tạm đã xoá")

    if failures:
        print("KẾT QUẢ: FAIL — " + "; ".join(failures), file=sys.stderr)
        return 1
    print("KẾT QUẢ: PASS — bản phục hồi khớp nguồn (head, bảng, số dòng, md5 nội dung).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
