"""Cấu hình môi trường Alembic cho VIP PHONE.

URL database lấy từ `DATABASE_URL` (qua `app.config`). KHÔNG hard-code
chuỗi kết nối hay credential trong repo.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401 - bắt buộc import để nạp metadata
from app.config import settings
from app.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    """URL database đang dùng.

    Ưu tiên giá trị người gọi đặt tường minh trên `Config` (test migration
    dùng cách này để trỏ vào database tạm). Nếu để trống thì lấy từ cấu hình
    ứng dụng (`DATABASE_URL`).
    """
    configured = config.get_main_option("sqlalchemy.url")
    return configured if configured else settings.database_url


#: Bảo đảm `context.configure(url=...)` khi chạy offline cũng thấy giá trị đúng.
config.set_main_option("sqlalchemy.url", _database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
