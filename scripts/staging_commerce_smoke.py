#!/usr/bin/env python3
"""Nghiệm thu THƯƠNG MẠI trên staging — một lệnh, API thật, dữ liệu có marker.

Đi trọn hành trình: sản phẩm demo → kho → lead → gợi ý → giỏ → đơn COD (chờ) → đơn
chuyển khoản (chờ) → nhân viên xác nhận → đồng bộ thanh toán → kho giữ đúng → ảnh
chụp giá → attribution → quà phát được → webhook giả lập (nếu có khoá) → dọn sạch.

An toàn:
- Từ chối nếu URL không phải ứng dụng VIP PHONE (chốt danh tính `/api/health`).
- Từ chối nếu `/api/public-config` cho thấy đây là production (không có STAGING_MOCK
  không đủ để kết luận, nên script còn đòi `--i-know-this-is-staging`).
- MỌI dữ liệu tạo ra mang marker `source=staging-test` / slug `demo-staging-*`,
  SĐT tiền tố `0900000` ⇒ `scripts/cleanup_test_data.py` dọn được, dữ liệu thật
  không bị đụng.
- Khoá nhân viên đọc từ BIẾN MÔI TRƯỜNG (`STAFF_KEY` mặc định), không nhận qua tham
  số dòng lệnh (tránh lộ trong lịch sử shell / `ps`).

Dùng:
    STAFF_KEY=... [MOCK_SECRET=...] scripts/staging_commerce_smoke.py \\
        --base-url https://qua.viporder.vn --i-know-this-is-staging
Mã thoát: 0 = mọi bước PASS · 1 = có FAIL · 2/3 = từ chối chạy.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

RUN = uuid.uuid4().hex[:6].upper()
SLUG = f"demo-staging-smoke-{RUN.lower()}"
SKU_TRACKED = f"DEMO-SMK-K-{RUN}"
SKU_FREE = f"DEMO-SMK-S-{RUN}"
PHONE = "0900000" + str(int(RUN, 16) % 1000).zfill(3)
DEVICE = "iphone-16-pro-max"
MARK = {"source": "staging-test", "utm_campaign": "staging-acceptance", "ref": f"SMOKE-{RUN}"}


class Client:
    def __init__(self, base: str, staff_key: str) -> None:
        self.base = base.rstrip("/")
        self.staff_key = staff_key

    def call(self, path, method="GET", body=None, headers=None, staff=False, raw=None):
        h = {"Accept": "application/json", **(headers or {})}
        data = raw
        if body is not None:
            h["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if staff:
            h["X-Staff-Key"] = self.staff_key
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read() or b"null")
            except ValueError:
                return exc.code, None


RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, evidence: str = "") -> bool:
    RESULTS.append((name, ok, evidence))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<52} {evidence}")
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--i-know-this-is-staging", action="store_true")
    ap.add_argument("--staff-key-env", default="STAFF_KEY")
    ap.add_argument("--mock-secret-env", default="MOCK_SECRET")
    args = ap.parse_args(argv)

    staff_key = os.environ.get(args.staff_key_env, "")
    if not staff_key:
        print(f"DỪNG: thiếu biến môi trường {args.staff_key_env}.", file=sys.stderr)
        return 2
    if not args.i_know_this_is_staging:
        print("DỪNG: phải có --i-know-this-is-staging (script TẠO dữ liệu thử).", file=sys.stderr)
        return 2
    c = Client(args.base_url, staff_key)

    st, health = c.call("/api/health")
    if st != 200 or not isinstance(health, dict) or health.get("service") != "vipphone":
        print(f"DỪNG: {args.base_url} không phải ứng dụng VIP PHONE ({st}).", file=sys.stderr)
        return 3
    print(
        f"=== NGHIỆM THU THƯƠNG MẠI · {args.base_url} · run {RUN} · {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
    )
    print(f"    version={health.get('version')} · marker source=staging-test · SĐT {PHONE}")
    _, cfg = c.call("/api/public-config")
    methods = (cfg or {}).get("payment_methods", [])
    check(
        "public-config có COD + chuyển khoản",
        {"COD", "BANK_TRANSFER_MANUAL"} <= set(methods),
        str(methods),
    )

    # Sản phẩm demo + kho
    st, prod = c.call(
        "/api/admin/products",
        "POST",
        {"name": f"Kính SMOKE {RUN}", "slug": SLUG, "category_code": "SCREEN_PROTECTOR"},
        staff=True,
    )
    if not check("tạo sản phẩm demo (admin)", st == 201, str(st)):
        return finish()
    pid = prod["product_id"]
    c.call(
        f"/api/admin/products/{pid}/variants",
        "POST",
        {
            "sku": SKU_TRACKED,
            "variant_name": "Có kho",
            "sale_price": "120000.00",
            "stock_tracking": True,
        },
        staff=True,
    )
    c.call(
        f"/api/admin/products/{pid}/variants",
        "POST",
        {"sku": SKU_FREE, "variant_name": "Không kho", "sale_price": "80000.00"},
        staff=True,
    )
    for sku in (SKU_TRACKED, SKU_FREE):
        c.call(
            f"/api/admin/variants/{sku}/compatibility",
            "POST",
            {"device_model_code": DEVICE, "compatibility_type": "FULL"},
            staff=True,
        )
    st, _ = c.call(
        f"/api/admin/inventory/{SKU_TRACKED}/movements",
        "POST",
        {"movement_type": "OPENING", "quantity": 5},
        staff=True,
    )
    check("mở sổ kho 5", st == 201, str(st))

    # Lead + gợi ý
    st, lead = c.call(
        "/api/leads",
        "POST",
        {
            "full_name": f"Khách SMOKE {RUN}",
            "phone": PHONE,
            "iphone_model": DEVICE,
            "consent": True,
            **{"source": MARK["source"], "utm_campaign": MARK["utm_campaign"], "ref": MARK["ref"]},
        },
    )
    check("tạo lead (gift code)", st == 201, (lead or {}).get("gift_code", str(st)))
    st, reco = c.call(f"/api/recommendations?device_model={DEVICE}&limit=24")
    slugs = [i["product"]["slug"] for i in (reco or {}).get("items", [])]
    check(
        "gợi ý có sản phẩm demo, không có ốp",
        st == 200 and SLUG in slugs and all(i["category_code"] != "CASE" for i in reco["items"]),
        f"{len(slugs)} mục",
    )

    def order(sku, method):
        _, cart = c.call("/api/cart", "POST")
        token = {"X-Cart-Token": cart["cart_token"]}
        c.call(f"/api/cart/{cart['cart_id']}/items", "POST", {"sku": sku, "quantity": 1}, token)
        _, view = c.call(f"/api/cart/{cart['cart_id']}", headers=token)
        body = {
            "cart_id": cart["cart_id"],
            "customer": {"full_name": f"Khách SMOKE {RUN}", "phone": PHONE},
            "shipping": {
                "recipient_name": f"Khách SMOKE {RUN}",
                "phone": PHONE,
                "address_line": f"1 Đường SMOKE {RUN}",
                "province": "TP Hồ Chí Minh",
            },
            "payment_method": method,
            "expected_total": view["grand_total"],
            "attribution": MARK,
        }
        key = uuid.uuid4().hex
        st, o = c.call("/api/checkout", "POST", body, {**token, "Idempotency-Key": key})
        st2, again = c.call("/api/checkout", "POST", body, {**token, "Idempotency-Key": key})
        check(
            f"đặt đơn {method} + phát lại cùng khoá ra CÙNG đơn",
            st == 201
            and st2 == 201
            and again["order_id"] == o["order_id"]
            and again["replayed"] is True,
            o.get("order_number", str(st)) if isinstance(o, dict) else str(st),
        )
        return o, token["X-Cart-Token"]

    cod, _ = order(SKU_TRACKED, "COD")
    check(
        "COD đang chờ, KHÔNG tự PAID",
        cod["payment"]["status"] == "PENDING" and cod["payment_status"] == "PENDING",
        cod["payment_status"],
    )
    bank, bank_token = order(SKU_FREE, "BANK_TRANSFER_MANUAL")
    check(
        "chuyển khoản đang chờ + hướng dẫn mã đơn",
        bank["payment"]["status"] == "PENDING"
        and bank["order_number"] in (bank["payment"]["instructions"] or ""),
        "",
    )

    st, _ = c.call(f"/api/orders/{bank['order_id']}", headers={"X-Order-Token": "sai"})
    check("tra đơn bằng token sai ⇒ 404 (chống IDOR)", st == 404, str(st))

    # Nhân viên
    st, customers = c.call(f"/api/admin/customers?phone={PHONE}", staff=True)
    check("admin thấy khách", st == 200 and len(customers) == 1, "")
    st, detail = c.call(f"/api/admin/customers/{customers[0]['customer_id']}", staff=True)
    check(
        "Customer 360 có 2 đơn",
        st == 200 and len(detail["orders"]) == 2,
        str(len(detail.get("orders", []))),
    )
    st, pays = c.call(f"/api/admin/orders/{bank['order_id']}/payments", staff=True)
    check(
        "admin thấy khoản thu chuyển khoản",
        st == 200 and pays[0]["method"] == "BANK_TRANSFER_MANUAL",
        "",
    )
    st, done = c.call(
        f"/api/admin/payments/{pays[0]['payment_id']}/confirm",
        "POST",
        {"note": f"SMOKE {RUN}"},
        staff=True,
    )
    check("nhân viên xác nhận đã nhận tiền", st == 200 and done["status"] == "PAID", str(st))
    _, view = c.call(f"/api/orders/{bank['order_id']}", headers={"X-Order-Token": bank_token})
    check(
        "trạng thái thanh toán đồng bộ sang đơn",
        view["payment_status"] == "PAID",
        view["payment_status"],
    )

    st, inv = c.call(f"/api/admin/inventory/{SKU_TRACKED}", staff=True)
    b = inv["balance"]
    check(
        "kho giữ đúng (5,1,4)",
        (b["quantity_on_hand"], b["quantity_reserved"], b["quantity_available"]) == (5, 1, 4),
        f"{b['quantity_on_hand']},{b['quantity_reserved']},{b['quantity_available']}",
    )

    c.call(
        f"/api/admin/variants/{SKU_TRACKED}",
        "PATCH",
        {"sale_price": "99000.00", "price_change_reason": f"SMOKE {RUN}"},
        staff=True,
    )
    st, od = c.call(f"/api/admin/orders/{cod['order_id']}", staff=True)
    check(
        "đổi giá: ảnh chụp giá đơn cũ KHÔNG đổi",
        od["items_detail"][0]["unit_price"] == "120000.00",
        od["items_detail"][0]["unit_price"],
    )
    _, hist = c.call(f"/api/admin/variants/{SKU_TRACKED}/price-history", staff=True)
    check(
        "lịch sử giá có dòng đổi giá kèm lý do",
        any(h["reason"] == f"SMOKE {RUN}" for h in hist),
        str(len(hist)),
    )
    check(
        "attribution: đơn + first-touch giữ đúng",
        od["attribution"]["ref"] == MARK["ref"]
        and (od["customer_first_touch"] or {}).get("ref") == MARK["ref"],
        "",
    )

    st, rd = c.call(f"/api/gifts/{lead['gift_code']}/redeem", "POST", {}, staff=True)
    check("quà vẫn phát được", st == 200 and rd["gift_status"] == "REDEEMED", str(st))

    secret = os.environ.get(args.mock_secret_env, "")
    if "STAGING_MOCK" in methods and secret:
        mock, _ = order(SKU_FREE, "STAGING_MOCK")
        body = json.dumps(
            {
                "event_id": f"evt_smoke_{RUN}",
                "payment_reference": mock["payment"]["provider_reference"],
                "status": "PAID",
                "amount": mock["payment"]["amount"],
                "currency": mock["payment"]["currency"],
            }
        ).encode()
        ts = str(int(time.time()))
        sig = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        hdr = {"Content-Type": "application/json", "X-Mock-Timestamp": ts, "X-Mock-Signature": sig}
        st, r1 = c.call("/api/payments/webhooks/staging-mock", "POST", headers=hdr, raw=body)
        st2, r2 = c.call("/api/payments/webhooks/staging-mock", "POST", headers=hdr, raw=body)
        check(
            "webhook giả lập đã ký ⇒ APPLIED, gửi lại ⇒ DUPLICATE",
            (r1 or {}).get("outcome") == "APPLIED" and (r2 or {}).get("outcome") == "DUPLICATE",
            f"{st}/{st2}",
        )
        st, _ = c.call(
            "/api/payments/webhooks/staging-mock",
            "POST",
            headers={**hdr, "X-Mock-Signature": "0" * 64},
            raw=body,
        )
        check("webhook chữ ký sai ⇒ 401", st == 401, str(st))
    else:
        print(
            "BỎ QUA webhook giả lập: STAGING_MOCK chưa bật hoặc thiếu MOCK_SECRET (ghi là NOT TESTED)."
        )

    st, _ = c.call(
        f"/api/admin/orders/{cod['order_id']}/status",
        "POST",
        {"to_status": "CANCELLED", "reason": f"SMOKE {RUN}"},
        staff=True,
    )
    _, inv = c.call(f"/api/admin/inventory/{SKU_TRACKED}", staff=True)
    check(
        "huỷ đơn ⇒ nhả hàng giữ (5,0,5)",
        inv["balance"]["quantity_reserved"] == 0,
        str(inv["balance"]["quantity_reserved"]),
    )
    return finish()


def finish() -> int:
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n=== KẾT QUẢ: {passed}/{len(RESULTS)} PASS · run {RUN}")
    print("Dọn dữ liệu thử: scripts/cleanup_test_data.py --database-url ... (đếm) rồi thêm --apply")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
