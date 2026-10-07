# Ảnh sản phẩm

Migration `0013_product_images` (additive).

## 1. Nguyên tắc

- **Không hotlink**: không có trường/tham số URL nào. Ảnh chỉ vào hệ thống bằng cách **tải byte lên**; DB giữ `storage_key`.
- **Không tin client**: `Content-Type` ∈ {png, jpeg, webp} **và** khớp magic bytes **và** Pillow mở + verify được.
  Trần dung lượng `MAX_IMAGE_BYTES` (mặc định 2 MB, kiểm `Content-Length` trước khi đọc), trần 6000 px/cạnh, 25 MP (chống decompression bomb).
- **Mã hoá lại** mọi ảnh ⇒ bỏ EXIF (GPS, máy chụp) và dữ liệu giấu trong file.
- `alt_text` **bắt buộc**. Tối đa **một** ảnh chính/sản phẩm (partial unique index); ảnh đầu tiên tự là ảnh chính;
  xoá ảnh chính ⇒ ảnh kế tiếp (`sort_order`, `id`) lên thay.
- Khoá lưu do máy chủ sinh: `products/<uuid32>.<ext>` ⇒ không đi ngược thư mục, không đè tệp.

## 2. Kho lưu — ranh giới production

`app/storage.py` — giao diện `ObjectStorage` (`put`, `delete`, `exists`, `public_url`).

| Môi trường | Hiện thực | Ghi chú |
|---|---|---|
| dev/test | `LocalFileStorage(MEDIA_ROOT)` | test dùng thư mục tạm |
| **staging** | `LocalFileStorage(/app/var/media)` trên **Docker named volume** `vipphone-staging-media` (deploy/common.sh) | bền qua các lần deploy/rollback; **chưa nằm trong `backup.sh`** (chỉ sao lưu DB) |
| production | **CHƯA QUYẾT** — khuyến nghị kho đối tượng S3-compatible + CDN | thêm lớp mới hiện thực `ObjectStorage`; bảng + API không đổi |

Phục vụ: `/media/...` cùng origin (CSP `img-src 'self'` không phải nới), `nosniff`, được cache (không `no-store`).

## 3. API quản trị (`require_staff`)

- `POST /api/admin/products/{product_id}/images?alt_text=&is_primary=&sort_order=` — body = byte ảnh, `Content-Type: image/png|jpeg|webp`.
- `PATCH /api/admin/products/{product_id}/images/{image_id}` — `{alt_text?, sort_order?, is_primary?}` (bỏ ảnh chính trực tiếp ⇒ 409; đặt ảnh khác làm chính).
- `DELETE /api/admin/products/{product_id}/images/{image_id}` — xoá tệp **sau** khi DB commit.

## 4. Công khai

`ProductOut.images = [{url, alt_text, is_primary, width, height}]` (ảnh chính đứng đầu). `/shop` hiện ảnh chính,
`/product/{slug}` hiện thư viện; có `width/height` để không giật bố cục, `loading="lazy"`.
