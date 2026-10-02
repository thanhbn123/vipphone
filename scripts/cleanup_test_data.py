#!/usr/bin/env python3
"""Dọn dữ liệu THỬ trên staging — chỉ xoá đúng thứ do test sinh ra.

VÌ SAO CẦN: nghiệm thu staging phải tạo lead thật trong database thật. Nếu không
có cách dọn, dữ liệu test sẽ nằm lẫn vĩnh viễn với dữ liệu khách — và tệ hơn, một
lệnh dọn viết ẩu có thể xoá nhầm lead của khách thật.

LUẬT AN TOÀN (cố ý khắt khe):
  1. Mặc định CHỈ ĐẾM, không xoá. Muốn xoá phải thêm `--apply`.
  2. Chỉ khớp lead có ĐÚNG dấu marker của test: `source=staging-test` HOẶC
     `utm_campaign=staging-acceptance`. Không suy đoán, không xoá "theo khoảng thời gian".
  3. Từ chối chạy khi `APP_ENV=production` — không có ngoại lệ, kể cả `--apply`.
  4. In ra bản ghi sẽ xoá TRƯỚC khi xoá, kèm số lượng và gift code.
  5. Chỉ xoá `leads`; `audit_events` giữ lại vết (đúng thiết kế ON DELETE SET NULL),
     nhưng nói rõ phần nào còn sót.

Dùng:
    scripts/cleanup_test_data.py --database-url "$DATABASE_URL"            # đếm
    scripts/cleanup_test_data.py --database-url "$DATABASE_URL" --apply    # xoá
"""

from __future__ import annotations

import argparse
import os
import sys

#: Dấu marker của dữ liệu test. PHẢI khớp `TEST_DATA_POLICY` trong tài liệu.
TEST_MARKERS = (
    ("source", "staging-test"),
    ("utm_campaign", "staging-acceptance"),
    #: Smoke tải gắn marker riêng để phân biệt với nghiệm thu chức năng.
    ("utm_campaign", "staging-load-smoke"),
)

#: Tiền tố số điện thoại dành riêng cho test (đúng định dạng VN, dễ nhận ra).
TEST_PHONE_PREFIX = "0900000"


def to_psycopg_dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dọn dữ liệu test trên staging")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--apply", action="store_true", help="thực sự xoá (mặc định chỉ đếm)")
    args = parser.parse_args()

    app_env = os.environ.get("APP_ENV", "").strip().lower()
    if app_env == "production":
        print(
            "TỪ CHỐI: APP_ENV=production. Script này KHÔNG BAO GIỜ chạy trên production.",
            file=sys.stderr,
        )
        return 2
    if not args.database_url:
        print("LỖI: thiếu --database-url hoặc DATABASE_URL.", file=sys.stderr)
        return 2

    dbname = args.database_url.rsplit("/", 1)[-1].split("?")[0]
    if "prod" in dbname.lower():
        print(f"TỪ CHỐI: tên database chứa 'prod' ({dbname!r}).", file=sys.stderr)
        return 2

    try:
        import psycopg
    except ImportError:
        print("LỖI: chưa cài psycopg.", file=sys.stderr)
        return 2

    where = " OR ".join(f"{col} = %s" for col, _ in TEST_MARKERS)
    params = [value for _, value in TEST_MARKERS]

    with (
        psycopg.connect(to_psycopg_dsn(args.database_url), connect_timeout=10) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT current_database()")
        print(f"database      : {cur.fetchone()[0]}")
        print(f"APP_ENV       : {app_env or '(không đặt)'}")
        print(f"marker        : {', '.join(f'{c}={v}' for c, v in TEST_MARKERS)}")
        print(
            f"số điện thoại : tiền tố {TEST_PHONE_PREFIX} (chỉ để nhận diện, KHÔNG dùng làm điều kiện xoá)"
        )
        print()

        cur.execute(f"SELECT count(*) FROM leads WHERE {where}", params)
        total = cur.fetchone()[0]

        cur.execute(
            f"SELECT gift_code, phone, full_name, gift_status, created_at FROM leads WHERE {where} "
            f"ORDER BY created_at LIMIT 20",
            params,
        )
        rows = cur.fetchall()

        print(f"lead khớp marker: {total}")
        for gift_code, phone, _name, status, created in rows:
            # Che bớt số điện thoại: kể cả dữ liệu test cũng không cần in đủ.
            shown = phone[:4] + "***" + phone[-3:] if phone and len(phone) >= 7 else "(?)"
            print(f"  {gift_code}  {shown}  {status:<9}  {created:%Y-%m-%d %H:%M}")
        if total > 20:
            print(f"  … và {total - 20} bản ghi nữa")

        if total == 0:
            print("\nKhông có gì để xoá.")
            return 0

        # Kiểm tra chéo: có lead nào KHÔNG khớp marker mà lại dùng SĐT test không?
        cur.execute(
            f"SELECT count(*) FROM leads WHERE phone LIKE %s AND NOT ({where})",
            [TEST_PHONE_PREFIX + "%", *params],
        )
        stray = cur.fetchone()[0]
        if stray:
            print(
                f"\n⚠️  CẢNH BÁO: {stray} lead dùng SĐT tiền tố test nhưng KHÔNG có marker.\n"
                "    Script CỐ Ý không xoá chúng — xoá theo số điện thoại là cách xoá nhầm\n"
                "    dữ liệu thật. Hãy gắn marker cho chúng hoặc xử lý tay."
            )

        if not args.apply:
            print(f"\nCHẾ ĐỘ CHỈ ĐẾM — chưa xoá gì. Thêm --apply để xoá {total} lead.")
            return 0

        cur.execute(f"DELETE FROM leads WHERE {where}", params)
        deleted = cur.rowcount
        conn.commit()
        print(f"\nĐÃ XOÁ {deleted} lead (khớp marker).")
        print(
            "Lưu ý: `audit_events` GIỮ LẠI vết (đúng thiết kế `ON DELETE SET NULL`), "
            "nên `lead_id`/`gift_code` trong audit VẪN CÒN."
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
