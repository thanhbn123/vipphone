#!/usr/bin/env python3
"""Kiểm TRÌNH DUYỆT THẬT trên một URL triển khai (staging) — CHỈ ĐỌC, không tạo dữ liệu.

Với mỗi engine (chromium/firefox/webkit) x mỗi độ rộng (320/375/390/430 mặc định)
x mỗi trang công khai, đo:

- trạng thái HTTP của trang (< 400)
- tràn ngang: `scrollWidth - clientWidth == 0`
- lỗi console / lỗi JS của trang
- tài nguyên hỏng: request cùng origin trả ≥ 400 hoặc thất bại (ảnh, css, js)
- mixed content: trang https mà có request http://

Trang sản phẩm lấy slug THẬT từ `/api/products` (không bịa). Không gửi form,
không tạo lead/đơn ⇒ chạy được bất cứ lúc nào, không cần dọn.

Dùng:
    scripts/staging_browser_check.py --base-url https://qua.viporder.vn
    scripts/staging_browser_check.py --base-url ... --browsers chromium --widths 390
Mã thoát: 0 = mọi ô PASS · 1 = có FAIL · 2 = không mở được trình duyệt / URL sai.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from urllib.parse import urlsplit

PAGES = ["/", "/shop", "/cart", "/checkout", "/order/success", "/success.html", "/redeem.html"]


def product_page(base: str) -> str | None:
    try:
        with urllib.request.urlopen(base + "/api/products?page_size=1", timeout=15) as r:
            items = json.loads(r.read()).get("items", [])
        return f"/product/{items[0]['slug']}" if items else None
    except Exception:
        return None


def _benign_console(text: str) -> bool:
    """Cảnh báo của CHÍNH trình duyệt khi trang chạy qua http không phải localhost:
    header COOP bị bỏ qua vì origin "không đáng tin". Không phải lỗi ứng dụng; trên
    https thật nó không xuất hiện (đo trên bản sao staging, 2026-10-08)."""
    return "Cross-Origin-Opener-Policy header has been ignored" in text and "untrustworthy" in text


def check_page(browser, base: str, path: str, width: int) -> list[str]:
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(base))
    problems: list[str] = []
    context = browser.new_context(viewport={"width": width, "height": 860})
    page = context.new_page()
    page.on(
        "console",
        lambda m: (
            m.type == "error"
            and not _benign_console(m.text)
            and problems.append(f"console: {m.text[:160]}")
        ),
    )
    page.on("pageerror", lambda e: problems.append(f"js: {str(e)[:160]}"))

    def on_response(response):
        url = response.url
        if url.startswith(origin) and response.status >= 400 and "/api/" not in url:
            problems.append(f"tài nguyên {response.status}: {url[len(origin) :][:120]}")

    page.on("response", on_response)
    page.on(
        "requestfailed",
        lambda req: (
            req.url.startswith(origin)
            and problems.append(f"request lỗi: {req.url[len(origin) :][:120]}")
        ),
    )
    page.on(
        "request",
        lambda req: (
            base.startswith("https://")
            and req.url.startswith("http://")
            and problems.append(f"mixed content: {req.url[:120]}")
        ),
    )
    try:
        response = page.goto(base + path, wait_until="load", timeout=60_000)
        if response is None or response.status >= 400:
            problems.append(f"trang trả {response.status if response else 'không phản hồi'}")
        page.wait_for_timeout(1500)  # để fetch của trang chạy xong
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        if overflow:
            problems.append(f"tràn ngang {overflow}px")
        broken = page.evaluate(
            "Array.from(document.images).filter(i => i.complete && i.naturalWidth === 0)"
            ".map(i => i.getAttribute('src'))"
        )
        problems += [f"ảnh hỏng: {src}" for src in broken]
    except Exception as exc:
        problems.append(f"lỗi điều hướng: {str(exc)[:160]}")
    finally:
        context.close()
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--browsers", default="chromium,firefox,webkit")
    ap.add_argument("--widths", default="320,375,390,430")
    args = ap.parse_args(argv)
    base = args.base_url.rstrip("/")

    try:
        with urllib.request.urlopen(base + "/api/health", timeout=15) as r:
            if json.loads(r.read()).get("service") != "vipphone":
                raise ValueError("không phải VIP PHONE")
    except Exception as exc:
        print(f"DỪNG: {base} không phải ứng dụng VIP PHONE ({exc}).", file=sys.stderr)
        return 2

    pages = list(PAGES)
    product = product_page(base)
    if product:
        pages.insert(2, product)
    else:
        print("GHI CHÚ: chưa có sản phẩm đang bán ⇒ bỏ trang chi tiết (NOT TESTED).")

    from playwright.sync_api import sync_playwright

    total = failed = 0
    with sync_playwright() as pw:
        for name in args.browsers.split(","):
            try:
                browser = getattr(pw, name.strip()).launch(headless=True)
            except Exception as exc:
                print(f"DỪNG: không mở được {name}: {str(exc)[:200]}", file=sys.stderr)
                return 2
            try:
                for width in (int(w) for w in args.widths.split(",")):
                    for path in pages:
                        problems = check_page(browser, base, path, width)
                        total += 1
                        if problems:
                            failed += 1
                        status = "PASS" if not problems else "FAIL"
                        print(f"{status}  {name:<8} {width:>4}px  {path}")
                        for p in problems:
                            print(f"        - {p}")
            finally:
                browser.close()
    print(f"\n=== KẾT QUẢ TRÌNH DUYỆT: {total - failed}/{total} ô PASS · {base}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
