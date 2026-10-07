"""Tầng kết nối database."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    echo=settings.sql_echo,
    pool_pre_ping=True,
    future=True,
    # KHÔNG để tham số SQL (tên, SĐT, địa chỉ...) lọt vào thông báo lỗi. Đo được:
    # trước đây `str(IntegrityError)` chứa "[parameters: {'n': '<họ tên>', 'p':
    # '<SĐT>'}]", và mã ghi log lỗi đó nguyên văn — tức là PII vào log.
    hide_parameters=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """Dependency FastAPI: một session cho mỗi request, luôn đóng."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
