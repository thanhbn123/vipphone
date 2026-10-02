# Tên miền + TLS cho staging — `qua.viporder.vn`

> ## ✅ TÊN MIỀN ĐÃ CÓ — CHỈ CÒN DÁN KHỐI CADDY
>
> | Mục | Trạng thái đo 2026-10-02 |
> |---|---|
> | `qua.viporder.vn` → `160.22.170.20` | ✅ **DNS ĐÚNG** (đo `dig`, TTL 300) |
> | Ứng dụng sẵn sàng | ✅ `PUBLIC_BASE_URL=https://qua.viporder.vn` · `ALLOWED_HOSTS=qua.viporder.vn,160.22.170.20` |
> | QR | ✅ **giải mã ra `https://qua.viporder.vn/redeem?code=…`** (zxing-cpp) |
> | TLS | ⏳ **chờ dán khối Caddy** — `deploy` không có sudo, Caddyfile là bind-mount **read-only** |
>
> **`DOMAIN = PASS`** · **`TLS = OWNER_PASTE_REQUIRED`**

## 0. VIỆC CẦN LÀM — dán đúng 4 dòng này

SSH vào máy staging rồi chạy:

```bash
sudo nano /srv/vip-staging-proxy/Caddyfile
```

Thêm **nguyên khối** này vào **cuối** file (giữ nguyên phần `cpn.viporder.vn` đang có):

```caddy
qua.viporder.vn {
    reverse_proxy 127.0.0.1:18080
}
```

Lưu lại, rồi nạp lại Caddy:

```bash
docker exec vip-staging-caddy caddy reload --config /etc/caddy/Caddyfile
```

Caddy **tự xin và tự gia hạn TLS** (Let's Encrypt) vì tên miền đã trỏ đúng. Không cần
làm gì thêm cho chứng chỉ.

**Tôi đã kiểm trước và xác nhận an toàn:** khối hiện có `cpn.viporder.vn → 127.0.0.1:8000`
giữ nguyên, còn vipphone nghe **18080** nên **không đụng nhau**. Việc thêm khối là **chỉ thêm**,
không sửa gì của dự án kia.

### Kiểm sau khi dán (1 lệnh)

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://qua.viporder.vn/api/health   # mong 200
```

Rồi **nhắn tôi một câu** — tôi chạy lại toàn bộ nghiệm thu qua HTTPS và trả kết quả cuối.

## 1. Việc Owner cần làm (một lần)

Chọn một tên miền staging và tạo bản ghi:

```
Loại : A
Tên  : staging.<domain-cua-anh>       (ví dụ staging.vipphone.vn)
Giá trị: 160.22.170.20
TTL  : 300 (tạm, để dễ đổi)
```

**Không đụng** `cpn.viporder.vn` — đó là staging của dự án khác đang chạy trên cùng máy.
**Không đụng** DNS production.

Kiểm sau khi tạo:

```bash
dig +short staging.<domain-cua-anh> A     # phải ra 160.22.170.20
```

## 2. Vì sao TÔI không tự làm được

`deploy` trên host **KHÔNG có sudo**:

```
$ sudo -n true
sudo: I'm sorry deploy. I'm afraid I can't do that
```

Hệ quả:
- Caddy đang phục vụ 80/443 là `vip-staging-caddy` — **dùng chung** với dự án khác, cấu hình
  nằm ở `/srv/vip-staging-proxy` **do root sở hữu**. Tôi **không sửa được**, và cũng
  **không nên** sửa: đó là reverse proxy của dự án khác.
- Không cài được gói hệ thống, không viết được unit systemd.

**Hai đường để Owner chọn:**

- **(a)** Cấp một trong hai: quyền ghi `/srv/vip-staging-proxy` cho `deploy`, **hoặc** sudo có
  giới hạn cho `deploy`. Rồi tôi thêm khối Caddy dưới đây.
- **(b)** Owner tự dán khối Caddy dưới đây vào Caddyfile của `vip-staging-caddy`.

## 3. Khối Caddy cần thêm (chính xác)

```caddy
staging.<domain-cua-anh> {
    encode gzip
    reverse_proxy 127.0.0.1:18080
}
```

Caddy **tự xin và tự gia hạn TLS** (Let's Encrypt) khi tên miền đã trỏ đúng — không cần
làm gì thêm cho chứng chỉ.

**Lưu ý:** khối hiện có (`cpn.viporder.vn` → `127.0.0.1:8000`) phải **giữ nguyên**.
Ứng dụng của dự án kia đang nghe cổng 8000; vipphone nghe **18080** nên không đụng nhau.

## 4. Sau khi có tên miền, tôi làm tiếp (không cần hỏi lại)

1. Đổi `PUBLIC_BASE_URL=https://staging.<domain>` và `ALLOWED_HOSTS=staging.<domain>` trong `.env` staging
2. Triển khai lại **đúng SHA** trên `develop`
3. `scripts/staging_preflight.sh` phải hết mục FAIL về https
4. Chạy lại **toàn bộ** nghiệm thu qua HTTPS, gồm decode QR (QR phải trỏ `https://…`)
5. E2E Chromium/Firefox/WebKit qua **HTTPS thật**
6. Cập nhật `docs/STAGING_ACCEPTANCE.md`

## 5. PostgreSQL KHÔNG được lộ ra ngoài

`vipphone-staging-pg` **không** publish cổng ra host (chỉ trong network Docker
`vipphone-staging-net`). Đã kiểm: chỉ `22/80/443` và `127.0.0.1:18080` mở. **Giữ nguyên** —
không thêm publish cho PostgreSQL.
