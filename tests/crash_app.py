"""Ứng dụng THỬ cho test che log: chính app thật + một route cố ý gây lỗi DB
KHÔNG được bắt, mang dữ liệu khách tổng hợp. Chỉ dùng trong test — không nằm
trong `app/`, không bao giờ được phục vụ ở staging/production."""

from __future__ import annotations

from sqlalchemy import text

from app.db import SessionLocal
from app.main import create_app

app = create_app()


@app.get("/__crash", include_in_schema=False)
def crash() -> None:
    session = SessionLocal()
    try:
        session.execute(
            text(
                "INSERT INTO leads (lead_id, gift_code, full_name, phone, iphone_model, "
                "iphone_year, consent) VALUES (gen_random_uuid(), 'X', :n, :p, 'm', 2020, true)"
            ),
            {"n": "Nguyễn Bí Mật", "p": "0112345678"},
        )
    finally:
        session.close()
