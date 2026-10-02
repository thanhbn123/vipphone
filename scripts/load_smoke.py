#!/usr/bin/env python3
"""Smoke tải nhẹ — LOCAL LOAD SMOKE, KHÔNG phải đo năng lực production.

VÌ SAO CẦN: mọi phép đo khác trong dự án đều là *đúng/sai*. Không có phép đo nào
trả lời "phục vụ được bao nhiêu". Script này trả lời câu hỏi hẹp hơn nhiều:
**"dưới tải nhẹ, có lỗi nào xuất hiện không, và độ trễ nằm ở đâu"** — đủ để phát
hiện sập sớm, KHÔNG đủ để nói gì về sức chịu tải thật.

Chỉ dùng thư viện chuẩn. KHÔNG gọi ra dịch vụ bên ngoài.

Dùng:
    scripts/load_smoke.py --base-url http://127.0.0.1:8770 --concurrency 8 --duration 15

⚠️  ĐỌC KẾT QUẢ CHO ĐÚNG:
    - Chạy trên MÁY, cùng máy với server ⇒ số đo bị nhiễu bởi chính máy đó.
    - Rate limit mặc định 10 lead/phút ⇒ POST sẽ bị 429. Đó là sản phẩm CHẠY ĐÚNG,
      không phải lỗi. Script tách riêng 429 để không trộn vào tỉ lệ lỗi.
"""

from __future__ import annotations

import argparse
import http.client
import json
import random
import statistics
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

#: ⚠️  `iphone_model` trong payload là **model_code**, KHÔNG phải tên hiển thị.
#: Bản đầu của script gửi "iPhone 16" (tên hiển thị) nên server trả 422 — script
#: sai, không phải server sai. Nay lấy model_code THẬT từ /api/catalog.
FALLBACK_MODEL_CODES = ["iphone-16", "iphone-15", "iphone-14"]
COLORS = ["Đen", "Trắng", "Xanh"]


@dataclass
class Stats:
    lock: threading.Lock = field(default_factory=threading.Lock)
    latencies: dict[str, list[float]] = field(default_factory=dict)
    errors: dict[str, list[str]] = field(default_factory=dict)
    rate_limited: int = 0
    total: int = 0

    def record(self, name: str, seconds: float) -> None:
        with self.lock:
            self.latencies.setdefault(name, []).append(seconds)
            self.total += 1

    def record_error(self, name: str, detail: str, *, rate_limited: bool = False) -> None:
        with self.lock:
            self.errors.setdefault(name, []).append(detail)
            self.total += 1
            if rate_limited:
                self.rate_limited += 1


_LOCAL = threading.local()


def _connection(parsed) -> http.client.HTTPConnection:
    """MỘT kết nối cho mỗi luồng, dùng lại (keep-alive).

    VÌ SAO: bản đầu mở kết nối mới cho mỗi request. Ở 6 luồng bắn liên tục, macOS
    cạn cổng tạm và trả `Errno 49 Can't assign requested address` — **lỗi của phép
    đo, không phải của server**. Giữ kết nối lại thì số đo mới nói về server.
    """
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=15)
        _LOCAL.conn = conn
    return conn


def request(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    headers: dict | None = None,
    timeout: float = 15.0,
) -> tuple[int, bytes]:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    payload = json.dumps(body).encode() if body is not None else None
    send_headers = {"Accept": "*/*", "Connection": "keep-alive"}
    if payload is not None:
        send_headers["Content-Type"] = "application/json"
    send_headers.update(headers or {})

    for attempt in (1, 2):
        try:
            conn = _connection(parsed)
            conn.request(method, path, body=payload, headers=send_headers)
            response = conn.getresponse()
            data = response.read()
            return response.status, data
        except Exception:
            # Kết nối cũ có thể đã bị server đóng — mở lại rồi thử ĐÚNG MỘT lần.
            _LOCAL.conn = None
            if attempt == 2:
                raise
    raise RuntimeError("không thể tới được server")


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[index]


def worker(
    name: str,
    fn,
    stats: Stats,
    stop_at: float,
    *,
    pause: float = 0.0,
) -> None:
    while time.monotonic() < stop_at:
        started = time.perf_counter()
        try:
            status, _ = fn()
        except Exception as exc:  # mạng hỏng, server chết
            stats.record_error(name, f"{type(exc).__name__}: {exc}")
            continue
        elapsed = time.perf_counter() - started
        if status == 429:
            stats.record_error(name, "HTTP 429", rate_limited=True)
        elif status >= 400:
            stats.record_error(name, f"HTTP {status}")
        else:
            stats.record(name, elapsed)
        if pause:
            time.sleep(pause)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local load smoke cho VIP PHONE")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--duration", type=float, default=15.0, help="giây")
    parser.add_argument("--staff-key", default="", help="khoá nhân viên để kiểm đường có xác thực")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    stats = Stats()
    stop_at = time.monotonic() + args.duration

    # Một gift code THẬT để kiểm đường tra cứu. Không có thì bỏ qua nhánh đó.
    # Lấy model_code THẬT — gửi tên hiển thị là 422.
    model_codes = list(FALLBACK_MODEL_CODES)
    try:
        status, payload = request("GET", f"{base}/api/catalog/iphone-models")
        if status == 200:
            rows = json.loads(payload)
            rows = rows.get("models", rows) if isinstance(rows, dict) else rows
            codes = [r["model_code"] for r in rows if r.get("model_code")]
            if codes:
                model_codes = codes
                print(f"danh mục: {len(codes)} model_code (ví dụ {codes[0]!r})")
    except Exception as exc:
        print(f"không đọc được danh mục ({type(exc).__name__}) — dùng mã dự phòng")

    gift_code = ""
    try:
        status, payload = request(
            "POST",
            f"{base}/api/leads",
            body={
                "full_name": "Load Smoke",
                "phone": f"09{random.randint(10_000_000, 99_999_999)}",
                "iphone_model": random.choice(model_codes),
                "case_color": random.choice(COLORS),
                "consent": True,
            },
        )
        if status in (200, 201):
            gift_code = json.loads(payload).get("gift_code", "")
    except Exception:
        pass
    print(f"gift code dùng cho nhánh tra cứu: {gift_code or '(không lấy được — bỏ qua)'}")

    scenarios: list[tuple[str, object, float]] = [
        ("GET / (landing)", lambda: request("GET", f"{base}/"), 0.0),
        (
            "GET /api/catalog/iphone-models",
            lambda: request("GET", f"{base}/api/catalog/iphone-models"),
            0.0,
        ),
        (
            "POST /api/leads",
            lambda: request(
                "POST",
                f"{base}/api/leads",
                body={
                    "full_name": "Load Smoke",
                    "phone": f"09{random.randint(10_000_000, 99_999_999)}",
                    "iphone_model": random.choice(model_codes),
                    "case_color": random.choice(COLORS),
                    "consent": True,
                },
            ),
            0.0,
        ),
    ]
    if gift_code:
        scenarios.append(
            (
                "GET /api/gifts/{code}/qr.png",
                lambda: request("GET", f"{base}/api/gifts/{gift_code}/qr.png"),
                0.0,
            )
        )
        staff_headers = {"X-Staff-Key": args.staff_key} if args.staff_key else {}

        def lookup():
            return request("GET", f"{base}/api/gifts/{gift_code}", headers=staff_headers)

        scenarios.append(("GET /api/gifts/{code} (nhân viên)", lookup, 0.0))

    threads: list[threading.Thread] = []
    per_scenario = max(1, args.concurrency // len(scenarios))
    for name, fn, pause in scenarios:
        for _ in range(per_scenario):
            threads.append(
                threading.Thread(
                    target=worker, args=(name, fn, stats, stop_at), kwargs={"pause": pause}
                )
            )

    print(f"chạy {len(threads)} luồng trong {args.duration:.0f}s …")
    started = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - started

    print("\n" + "=" * 78)
    print(f"{'kịch bản':<34}{'req':>6}{'lỗi':>6}{'429':>6}{'p50':>9}{'p95':>9}{'max':>9}")
    print("-" * 78)
    total_ok = total_err = 0
    for name, _, _ in scenarios:
        lat = stats.latencies.get(name, [])
        errs = stats.errors.get(name, [])
        total_ok += len(lat)
        total_err += len(errs)
        limited = sum(1 for e in errs if e == "HTTP 429")
        print(
            f"{name:<34}{len(lat) + len(errs):>6}{len(errs) - limited:>6}{limited:>6}"
            f"{percentile(lat, 0.50) * 1000:>8.1f}ms{percentile(lat, 0.95) * 1000:>8.1f}ms"
            f"{(max(lat) if lat else 0) * 1000:>8.1f}ms"
        )
    print("-" * 78)
    all_lat = [v for values in stats.latencies.values() for v in values]
    err_rate = (total_err / stats.total * 100) if stats.total else 0.0
    print(
        f"TỔNG: {stats.total} request trong {wall:.1f}s "
        f"({stats.total / wall:.0f} req/s) · lỗi {total_err} ({err_rate:.1f}%) "
        f"· 429 {stats.rate_limited}"
    )
    print(
        f"độ trễ gộp: p50={percentile(all_lat, 0.50) * 1000:.1f}ms "
        f"p95={percentile(all_lat, 0.95) * 1000:.1f}ms "
        f"trung bình={statistics.mean(all_lat) * 1000 if all_lat else 0:.1f}ms"
    )

    if stats.errors:
        print("\nchi tiết lỗi (tối đa 5 mỗi kịch bản):")
        for name, errs in stats.errors.items():
            for detail in errs[:5]:
                print(f"  {name}: {detail}")

    # Cảnh báo phải ĐÚNG với nơi chạy. Bản cũ hardcode "LOCAL ... cùng máy với server",
    # nên khi chạy từ máy khác vào staging nó in ra một câu SAI — tự làm hỏng bằng chứng.
    from urllib.parse import urlparse

    host = urlparse(base).hostname or ""
    is_loopback = host in {"127.0.0.1", "localhost", "::1"} or host.startswith("127.")
    print("\n⚠️  LOAD SMOKE — KHÔNG phải benchmark năng lực production.")
    if is_loopback:
        print("    Đích là loopback ⇒ chạy CÙNG MÁY với server ⇒ số đo bị nhiễu.")
    else:
        print(f"    Đích là {host} ⇒ chạy QUA MẠNG tới máy khác.")
        print("    Nhưng tải vẫn NHỎ và ngắn ⇒ KHÔNG suy ra được năng lực chịu tải.")
    # Lỗi thật (không tính 429 do rate limit chạy ĐÚNG) mới là đáng lo.
    return 1 if total_err - stats.rate_limited > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
