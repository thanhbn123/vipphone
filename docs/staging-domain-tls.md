# Tên miền + TLS cho staging — cấu hình CHÍNH XÁC cần Owner cấp

> Trạng thái đo ngày **2026-10-02**: **CHƯA CÓ** tên miền nào của vipphone trỏ về staging.
>
> | Tên miền thử | Kết quả đo |
> |---|---|
> | `staging.vipphone.vn` | **không có bản ghi A** |
> | `vipphone.vn` | **không có bản ghi A** |
> | `vipphone.viporder.vn` | **không có bản ghi A** |
> | `staging.vipphone.com` | `13.248.169.48` — **KHÔNG phải** host staging |
> | `cpn.viporder.vn` | `160.22.170.20` — nhưng là domain của **dự án khác** |
>
> ⇒ **`DOMAIN = OWNER_ACTION_REQUIRED`** · **`TLS = BLOCKED_OWNER_DOMAIN`**

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
