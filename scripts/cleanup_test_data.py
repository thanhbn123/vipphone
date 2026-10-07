#!/usr/bin/env python3
"""Dọn dữ liệu THỬ trên staging — chỉ xoá đúng thứ do test sinh ra.

VÌ SAO CẦN: nghiệm thu staging phải tạo lead/đơn thật trong database thật. Nếu
không có cách dọn, dữ liệu test nằm lẫn vĩnh viễn với dữ liệu khách — và tệ hơn,
một lệnh dọn viết ẩu có thể xoá nhầm dữ liệu của khách thật.

LUẬT AN TOÀN (cố ý khắt khe):
  1. Mặc định CHỈ ĐẾM, không xoá. Muốn xoá phải thêm `--apply`.
  2. Chỉ khớp dòng có ĐÚNG dấu marker của test (xem `TEST_DATA_POLICY` bên dưới).
     Không suy đoán, không xoá "theo khoảng thời gian", không xoá theo số điện thoại.
  3. Từ chối chạy khi `APP_ENV=production` hoặc tên database chứa `prod`.
  4. In số lượng TỪNG BẢNG sẽ xoá TRƯỚC khi xoá.
  5. Xoá trong MỘT giao dịch; sau khi xoá ĐẾM LẠI — còn sót marker ⇒ rollback.
  6. Dòng KHÔNG có marker không bao giờ bị xoá. Khách hàng chỉ bị xoá khi MỌI lead
     và MỌI đơn của họ đều mang marker. Sản phẩm demo còn nằm trong đơn thật ⇒ giữ
     lại và báo ra (không phá bằng chứng giao dịch).
  7. `audit_events` giữ vết (ON DELETE SET NULL).

TEST_DATA_POLICY — dấu marker:
  - lead:     source = 'staging-test' HOẶC utm_campaign ∈ {staging-acceptance, staging-load-smoke}
  - đơn:      cùng bộ marker trên cột `orders.source` / `orders.utm_campaign`
              (checkout gửi `attribution`), HOẶC đơn của một giỏ đã đặt từ khách test
  - sản phẩm: slug bắt đầu bằng `demo-staging-`

Dùng:
    scripts/cleanup_test_data.py --database-url "$DATABASE_URL"            # đếm
    scripts/cleanup_test_data.py --database-url "$DATABASE_URL" --apply    # xoá
"""

from __future__ import annotations

import argparse
import os
import sys

#: Dấu marker của dữ liệu test. PHẢI khớp `TEST_DATA_POLICY` ở trên và trong tài liệu.
TEST_MARKERS = (
    ("source", "staging-test"),
    ("utm_campaign", "staging-acceptance"),
    #: Smoke tải gắn marker riêng để phân biệt với nghiệm thu chức năng.
    ("utm_campaign", "staging-load-smoke"),
)

#: Sản phẩm demo/test: slug có tiền tố này (đã dùng từ nghiệm thu G14).
TEST_PRODUCT_SLUG_PREFIX = "demo-staging-"

#: Tiền tố số điện thoại dành riêng cho test (đúng định dạng VN, dễ nhận ra).
TEST_PHONE_PREFIX = "0900000"


def to_psycopg_dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def marker_where(alias: str) -> str:
    return (
        "("
        + " OR ".join(f"{alias}.{col} = %(m{i})s" for i, (col, _) in enumerate(TEST_MARKERS))
        + ")"
    )


def marker_params() -> dict[str, str]:
    params = {f"m{i}": value for i, (_, value) in enumerate(TEST_MARKERS)}
    params["slug_prefix"] = TEST_PRODUCT_SLUG_PREFIX + "%"
    return params


#: Tập id dữ liệu test, tính bằng CTE dùng chung cho cả ĐẾM lẫn XOÁ — một định
#: nghĩa duy nhất, không thể "đếm một kiểu, xoá một kiểu".
SCOPE_SQL = f"""
CREATE TEMP TABLE _t_leads ON COMMIT DROP AS
    SELECT l.id FROM leads l WHERE {marker_where("l")};
CREATE TEMP TABLE _t_orders ON COMMIT DROP AS
    SELECT o.id FROM orders o WHERE {marker_where("o")};
-- Khách test: có ít nhất một lead/đơn marker VÀ KHÔNG có lead/đơn nào thiếu marker.
CREATE TEMP TABLE _t_customers ON COMMIT DROP AS
    SELECT c.id FROM customers c
    WHERE (EXISTS (SELECT 1 FROM leads l WHERE l.customer_id = c.id AND l.id IN (SELECT id FROM _t_leads))
        OR EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id AND o.id IN (SELECT id FROM _t_orders)))
      AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.customer_id = c.id AND l.id NOT IN (SELECT id FROM _t_leads))
      AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id AND o.id NOT IN (SELECT id FROM _t_orders));
CREATE TEMP TABLE _t_products ON COMMIT DROP AS
    SELECT p.id FROM products p WHERE p.slug LIKE %(slug_prefix)s;
-- Sản phẩm demo mà đơn THẬT (không marker) còn tham chiếu ⇒ GIỮ, không xoá.
CREATE TEMP TABLE _t_products_blocked ON COMMIT DROP AS
    SELECT DISTINCT v.product_id AS id FROM order_items oi
    JOIN product_variants v ON v.id = oi.sku_id
    WHERE v.product_id IN (SELECT id FROM _t_products)
      AND oi.order_id NOT IN (SELECT id FROM _t_orders);
DELETE FROM _t_products WHERE id IN (SELECT id FROM _t_products_blocked);
CREATE TEMP TABLE _t_skus ON COMMIT DROP AS
    SELECT v.id FROM product_variants v WHERE v.product_id IN (SELECT id FROM _t_products);
"""

#: (nhãn, câu đếm) — theo đúng thứ tự xoá.
COUNTS = [
    (
        "payment_events",
        "SELECT count(*) FROM payment_events WHERE payment_id IN "
        "(SELECT id FROM payments WHERE order_id IN (SELECT id FROM _t_orders))",
    ),
    ("payments", "SELECT count(*) FROM payments WHERE order_id IN (SELECT id FROM _t_orders)"),
    (
        "inventory_movements (SKU demo)",
        "SELECT count(*) FROM inventory_movements WHERE sku_id IN (SELECT id FROM _t_skus)",
    ),
    (
        "order_items",
        "SELECT count(*) FROM order_items WHERE order_id IN (SELECT id FROM _t_orders)",
    ),
    ("orders", "SELECT count(*) FROM _t_orders"),
    ("leads", "SELECT count(*) FROM _t_leads"),
    ("customers", "SELECT count(*) FROM _t_customers"),
    ("products (demo)", "SELECT count(*) FROM _t_products"),
    ("products giữ lại (còn trong đơn thật)", "SELECT count(*) FROM _t_products_blocked"),
]

HELD_BY_TEST_ORDERS = """
    SELECT sku_id, sum(delta_reserved) AS held FROM inventory_movements
    WHERE order_id IN (SELECT id FROM _t_orders) AND sku_id NOT IN (SELECT id FROM _t_skus)
    GROUP BY sku_id HAVING sum(delta_reserved) > 0
"""

DELETES = [
    # Kho của SKU THẬT: KHÔNG xoá sổ cái (số dư = tổng sổ cái — xoá dòng là làm lệch).
    # (1) Phần đơn test còn đang GIỮ ⇒ ghi một dòng RELEASE + trả lại số dư.
    "INSERT INTO inventory_movements (sku_id, movement_type, delta_on_hand, delta_reserved, "
    "order_id, actor, reason) SELECT sku_id, 'RELEASE', 0, -held, NULL, 'cleanup:test-data', "
    f"'Dọn dữ liệu test' FROM ({HELD_BY_TEST_ORDERS}) x",
    "UPDATE inventory_balances b SET quantity_reserved = b.quantity_reserved - x.held "
    f"FROM ({HELD_BY_TEST_ORDERS}) x WHERE b.sku_id = x.sku_id",
    # (2) Tách liên kết tới đơn test (giữ nguyên dòng sổ cái).
    "UPDATE inventory_movements SET order_id = NULL WHERE order_id IN (SELECT id FROM _t_orders)",
    # SKU demo: xoá trọn sổ + số dư (cả sản phẩm sẽ bị xoá).
    "DELETE FROM inventory_movements WHERE sku_id IN (SELECT id FROM _t_skus)",
    "DELETE FROM inventory_balances WHERE sku_id IN (SELECT id FROM _t_skus)",
    "DELETE FROM payments WHERE order_id IN (SELECT id FROM _t_orders)",
    "DELETE FROM carts WHERE id IN (SELECT cart_id FROM orders WHERE id IN (SELECT id FROM _t_orders))",
    "DELETE FROM orders WHERE id IN (SELECT id FROM _t_orders)",
    "DELETE FROM leads WHERE id IN (SELECT id FROM _t_leads)",
    "DELETE FROM customers WHERE id IN (SELECT id FROM _t_customers)",
    "DELETE FROM products WHERE id IN (SELECT id FROM _t_products)",
]


def refuse(message: str) -> int:
    print(f"TỪ CHỐI: {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dọn dữ liệu test trên staging")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--apply", action="store_true", help="thực sự xoá (mặc định chỉ đếm)")
    args = parser.parse_args(argv)

    app_env = os.environ.get("APP_ENV", "").strip().lower()
    if app_env == "production":
        return refuse("APP_ENV=production. Script này KHÔNG BAO GIỜ chạy trên production.")
    if not args.database_url:
        print("LỖI: thiếu --database-url hoặc DATABASE_URL.", file=sys.stderr)
        return 2
    dbname = args.database_url.rsplit("/", 1)[-1].split("?")[0]
    if "prod" in dbname.lower():
        return refuse(f"tên database chứa 'prod' ({dbname!r}).")

    try:
        import psycopg
    except ImportError:
        print("LỖI: chưa cài psycopg.", file=sys.stderr)
        return 2

    params = marker_params()
    with (
        psycopg.connect(to_psycopg_dsn(args.database_url), connect_timeout=10) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT current_database()")
        print(f"database      : {cur.fetchone()[0]}")
        print(f"APP_ENV       : {app_env or '(không đặt)'}")
        print(f"marker        : {', '.join(f'{c}={v}' for c, v in TEST_MARKERS)}")
        print(f"sản phẩm demo : slug LIKE '{TEST_PRODUCT_SLUG_PREFIX}%'")
        print()

        for statement in SCOPE_SQL.strip().split(";\n"):
            if statement.strip():
                cur.execute(statement, params)

        counts: dict[str, int] = {}
        for label, sql in COUNTS:
            cur.execute(sql)
            counts[label] = cur.fetchone()[0]
            print(f"  {label:<40} {counts[label]}")

        cur.execute(
            "SELECT count(*) FROM leads WHERE phone LIKE %(p)s AND id NOT IN (SELECT id FROM _t_leads)",
            {"p": TEST_PHONE_PREFIX + "%"},
        )
        stray = cur.fetchone()[0]
        if stray:
            print(
                f"\n⚠️  CẢNH BÁO: {stray} lead dùng SĐT tiền tố test nhưng KHÔNG có marker.\n"
                "    Script CỐ Ý không xoá chúng — xoá theo số điện thoại là cách xoá nhầm\n"
                "    dữ liệu thật. Hãy gắn marker cho chúng hoặc xử lý tay."
            )

        total = sum(v for k, v in counts.items() if not k.startswith("products giữ"))
        if total == 0:
            print("\nKhông có gì để xoá.")
            conn.rollback()
            return 0
        if not args.apply:
            print("\nCHẾ ĐỘ CHỈ ĐẾM — chưa xoá gì. Thêm --apply để xoá.")
            conn.rollback()
            return 0

        for sql in DELETES:
            cur.execute(sql)

        # Kiểm lại TRONG cùng giao dịch: còn sót marker ⇒ rollback toàn bộ.
        cur.execute(f"SELECT count(*) FROM leads l WHERE {marker_where('l')}", params)
        left_leads = cur.fetchone()[0]
        cur.execute(f"SELECT count(*) FROM orders o WHERE {marker_where('o')}", params)
        left_orders = cur.fetchone()[0]
        if left_leads or left_orders:
            conn.rollback()
            print(
                f"LỖI: sau khi xoá vẫn còn {left_leads} lead / {left_orders} đơn marker — ĐÃ ROLLBACK.",
                file=sys.stderr,
            )
            return 1
        conn.commit()

    print("\nĐÃ XOÁ (một giao dịch, đã kiểm lại: 0 lead / 0 đơn marker còn sót).")
    print(
        "Lưu ý: `audit_events` GIỮ LẠI vết (ON DELETE SET NULL). Tệp ảnh của sản phẩm demo "
        "(nếu có) nằm trong volume media — dọn bằng tay nếu cần."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
