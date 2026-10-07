"""Ảnh sản phẩm. Thiết kế: `docs/product-images.md`.

Bảo vệ: chỉ nhận byte ảnh thật (magic bytes + Pillow) · EXIF bị xoá · không có
đường khai URL ngoài (không hotlink) · ảnh chính duy nhất · alt bắt buộc ·
ảnh phục vụ cùng origin · quyền nhân viên.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import text

from app.config import settings

pytestmark = pytest.mark.integration


def png_bytes(color=(200, 30, 40), size=(40, 30), exif: bool = False, fmt="PNG") -> bytes:
    image = Image.new("RGB", size, color)
    out = io.BytesIO()
    kwargs = {}
    if exif:
        data = Image.Exif()
        data[0x010F] = "MayChupBiMat"  # Make
        kwargs["exif"] = data.tobytes()
    image.save(out, fmt, **kwargs)
    return out.getvalue()


@pytest.fixture
def product_id(client, staff_headers) -> str:
    r = client.post(
        "/api/admin/products",
        json={"name": "Ốp có ảnh", "slug": "op-co-anh", "category_code": "CASE"},
        headers=staff_headers,
    )
    pid = r.json()["product_id"]
    client.post(
        f"/api/admin/products/{pid}/variants",
        json={"sku": "OP-ANH", "variant_name": "Đen", "sale_price": "1.00"},
        headers=staff_headers,
    )
    return pid


def upload(client, staff_headers, pid, data, *, ctype="image/png", alt="Ốp màu đỏ", **params):
    return client.post(
        f"/api/admin/products/{pid}/images",
        params={"alt_text": alt, **params},
        content=data,
        headers={**staff_headers, "Content-Type": ctype},
    )


def test_upload_png_served_same_origin(client, staff_headers, product_id):
    r = upload(client, staff_headers, product_id, png_bytes())
    assert r.status_code == 201, r.text
    image = r.json()["images"][0]
    assert image["url"].startswith("/media/products/") and image["url"].endswith(".png")
    assert (image["width"], image["height"], image["is_primary"]) == (40, 30, True)
    served = client.get(image["url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"
    assert Image.open(io.BytesIO(served.content)).size == (40, 30)

    public = client.get("/api/products/op-co-anh").json()["images"]
    assert public == [
        {
            "url": image["url"],
            "alt_text": "Ốp màu đỏ",
            "is_primary": True,
            "width": 40,
            "height": 30,
        }
    ]
    assert "storage_key" not in str(public) and "image_id" not in str(public)


def test_exif_is_stripped(client, staff_headers, product_id):
    raw = png_bytes(fmt="JPEG", exif=True)
    assert b"MayChupBiMat" in raw
    r = upload(client, staff_headers, product_id, raw, ctype="image/jpeg")
    assert r.status_code == 201, r.text
    stored = client.get(r.json()["images"][0]["url"]).content
    assert b"MayChupBiMat" not in stored
    assert not Image.open(io.BytesIO(stored)).getexif()


@pytest.mark.parametrize(
    "data, ctype, status, code",
    [
        (
            b"<svg xmlns='http://www.w3.org/2000/svg'/>",
            "image/svg+xml",
            415,
            "UNSUPPORTED_IMAGE_TYPE",
        ),
        (b"GIF89a....", "image/gif", 415, "UNSUPPORTED_IMAGE_TYPE"),
        (b"<html><script>alert(1)</script>", "image/png", 422, "IMAGE_TYPE_MISMATCH"),
        (b"\x89PNG\r\n\x1a\n" + b"rac" * 10, "image/png", 422, "INVALID_IMAGE"),
        (b"", "image/png", 422, "EMPTY_IMAGE"),
    ],
)
def test_rejects_non_images_and_mismatched_types(
    client, staff_headers, product_id, db, data, ctype, status, code
):
    r = upload(client, staff_headers, product_id, data, ctype=ctype)
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code
    assert db.execute(text("SELECT count(*) FROM product_images")).scalar_one() == 0


def test_jpeg_declared_as_png_rejected(client, staff_headers, product_id):
    r = upload(client, staff_headers, product_id, png_bytes(fmt="JPEG"), ctype="image/png")
    assert r.status_code == 422 and r.json()["error"]["code"] == "IMAGE_TYPE_MISMATCH"


def test_too_large_rejected_before_reading(client, staff_headers, product_id, monkeypatch):
    monkeypatch.setattr(settings, "max_image_bytes", 10_000)
    r = upload(client, staff_headers, product_id, png_bytes() + b"\0" * 20_000)
    assert r.status_code == 413


def test_alt_text_required(client, staff_headers, product_id):
    assert upload(client, staff_headers, product_id, png_bytes(), alt="   ").status_code == 422
    r = client.post(
        f"/api/admin/products/{product_id}/images",
        content=png_bytes(),
        headers={**staff_headers, "Content-Type": "image/png"},
    )
    assert r.status_code == 422


def test_no_url_based_image_input_exists(client, staff_headers, product_id):
    """Không có cách nào khai ảnh bằng URL ngoài (chống hotlink)."""
    r = client.post(
        f"/api/admin/products/{product_id}/images",
        params={"alt_text": "x", "url": "https://example.com/a.png"},
        json={"url": "https://example.com/a.png"},
        headers=staff_headers,
    )
    assert r.status_code in (415, 422)
    from app.models import ProductImage

    assert "url" not in {c.name for c in ProductImage.__table__.columns}


def test_single_primary_and_ordering(client, staff_headers, product_id, db):
    a = upload(client, staff_headers, product_id, png_bytes(color=(1, 1, 1)), alt="A", sort_order=5)
    b = upload(client, staff_headers, product_id, png_bytes(color=(2, 2, 2)), alt="B", sort_order=1)
    c = upload(
        client,
        staff_headers,
        product_id,
        png_bytes(color=(3, 3, 3)),
        alt="C",
        sort_order=3,
        is_primary=True,
    )
    assert [i["alt_text"] for i in c.json()["images"]] == ["C", "B", "A"]
    assert [i["is_primary"] for i in c.json()["images"]] == [True, False, False]
    assert (
        db.execute(text("SELECT count(*) FROM product_images WHERE is_primary")).scalar_one() == 1
    )
    del a, b

    images = c.json()["images"]
    b_id = images[1]["image_id"]
    r = client.patch(
        f"/api/admin/products/{product_id}/images/{b_id}",
        json={"is_primary": True, "alt_text": "B mới"},
        headers=staff_headers,
    )
    first = r.json()["images"][0]
    assert (first["alt_text"], first["is_primary"]) == ("B mới", True)
    assert (
        db.execute(text("SELECT count(*) FROM product_images WHERE is_primary")).scalar_one() == 1
    )


def test_cannot_unset_primary_directly(client, staff_headers, product_id):
    r = upload(client, staff_headers, product_id, png_bytes())
    image_id = r.json()["images"][0]["image_id"]
    r = client.patch(
        f"/api/admin/products/{product_id}/images/{image_id}",
        json={"is_primary": False},
        headers=staff_headers,
    )
    assert r.status_code == 409


def test_delete_promotes_next_and_removes_file(client, staff_headers, product_id):
    first = upload(client, staff_headers, product_id, png_bytes(), alt="1").json()["images"][0]
    upload(client, staff_headers, product_id, png_bytes(color=(9, 9, 9)), alt="2", sort_order=2)
    path = Path(settings.media_root) / first["url"].removeprefix("/media/")
    assert path.is_file()
    r = client.delete(
        f"/api/admin/products/{product_id}/images/{first['image_id']}", headers=staff_headers
    )
    assert [(i["alt_text"], i["is_primary"]) for i in r.json()["images"]] == [("2", True)]
    assert not path.exists()
    assert client.get(first["url"]).status_code == 404


def test_image_of_other_product_not_addressable(client, staff_headers, product_id):
    r = upload(client, staff_headers, product_id, png_bytes())
    image_id = r.json()["images"][0]["image_id"]
    other = client.post(
        "/api/admin/products",
        json={"name": "Khác", "slug": "khac", "category_code": "CASE"},
        headers=staff_headers,
    ).json()["product_id"]
    r = client.delete(f"/api/admin/products/{other}/images/{image_id}", headers=staff_headers)
    assert r.status_code == 404


def test_media_path_traversal_blocked(client):
    for path in (
        "/media/../app/config.py",
        "/media/%2e%2e/app/config.py",
        "/media/products/../../.env",
    ):
        assert client.get(path).status_code == 404


def test_image_routes_require_staff(client, staff_headers, product_id):
    r = client.post(
        f"/api/admin/products/{product_id}/images",
        params={"alt_text": "x"},
        content=png_bytes(),
        headers={"Content-Type": "image/png"},
    )
    assert r.status_code == 401


def test_shop_list_includes_primary_image(client, staff_headers, product_id):
    upload(client, staff_headers, product_id, png_bytes(), alt="Ảnh chính")
    item = client.get("/api/products").json()["items"][0]
    assert item["images"][0]["alt_text"] == "Ảnh chính"
