# VIP PHONE Starter

Bộ starter cho landing nhận ốp VIP PHONE miễn phí.

## Có gì trong gói này

- `index.html`: landing page thu lead
- `success.html`: trang hiển thị mã nhận quà
- `redeem.html`: giao diện nhân viên xác nhận phát quà
- `data/iphone-models.json`: danh sách model iPhone theo năm
- `assets/js/app.js`: validation, lead capture, chống submit trùng cơ bản
- `assets/js/success.js`: đọc lead gần nhất và hiển thị mã quà
- `assets/js/redeem.js`: xác nhận redeem một lần
- `assets/js/qr-lite.js`: placeholder QR-like local
- `docs/architecture.md`: kiến trúc
- `docs/lead-schema.md`: schema lead
- `.github/workflows/ci.yml`: CI kiểm tra file cơ bản

## Chạy local

Không nên mở `index.html` trực tiếp bằng `file://` vì browser có thể chặn `fetch()`.

Ví dụ:

```bash
python3 -m http.server 8080
```

Sau đó mở:

```text
http://localhost:8080
```

## Lưu ý quan trọng trước production

Starter hiện dùng `localStorage` để demo luồng, vì repo ban đầu chưa có backend.

Điều này có nghĩa:

- lead chỉ tồn tại trên trình duyệt đã đăng ký;
- nhân viên ở máy khác không nhìn thấy lead;
- chưa có database;
- chưa có xác thực nhân viên;
- chưa có chống spam/phá form ở mức server;
- chưa có CRM/webhook.

`qr-lite.js` chỉ là placeholder trực quan để demo luồng. Trước production cần thay bằng QR chuẩn thông qua thư viện thật hoặc backend service.

## Bước production tiếp theo

Khuyến nghị thêm backend:

- `POST /api/leads`
- `GET /api/gifts/{gift_code}`
- `POST /api/gifts/{gift_code}/redeem`

Database tối thiểu:

- PostgreSQL
- bảng `leads`
- bảng `gift_redemptions` hoặc audit log

Nên có:

- Cloudflare Turnstile/reCAPTCHA
- rate limit
- staff authentication
- audit log
- webhook CRM
- GTM/GA4/Meta Pixel
- export CSV/XLSX lead

## Đẩy lên GitHub

```bash
git init
git add .
git commit -m "feat: bootstrap VIP PHONE gift lead funnel"
git branch -M main
git remote add origin https://github.com/thanhbn123/vipphone.git
git push -u origin main
```

Nếu repo đã được tạo và clone sẵn thì chỉ cần copy file vào repo rồi:

```bash
git add .
git commit -m "feat: bootstrap VIP PHONE gift lead funnel"
git push
```
