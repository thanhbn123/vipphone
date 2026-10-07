"""Cấu hình test cho VIP PHONE.

QUAN TRỌNG — biến môi trường được đặt ở ĐẦU file này, TRƯỚC khi import bất kỳ
module `app.*` nào, vì `app.config.settings` được cache bằng `lru_cache`.

CHỐT AN TOÀN: test chỉ chạy trên database có tên kết thúc bằng `_test`.
Nếu không, dừng ngay — tránh xoá nhầm database dev/staging/production.
"""

from __future__ import annotations

import os

from sqlalchemy.engine import make_url

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://vipphone:vipphone@localhost:5432/vipphone_test"

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)

_test_db_name = make_url(TEST_DATABASE_URL).database or ""
if not _test_db_name.endswith("_test"):
    raise RuntimeError(
        "TỪ CHỐI CHẠY TEST: TEST_DATABASE_URL phải trỏ tới database có tên kết thúc "
        f"bằng '_test' (đang là {_test_db_name!r}). "
        "Test sẽ xoá sạch dữ liệu trong database đó."
    )

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SQL_ECHO"] = "false"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"
# Khoá nhân viên dùng trong test.
#
# ⚠️  CỐ Ý ĐỂ ĐỘ PHỨC TẠP THẤP. Đừng "cải tiến" thành chuỗi hex ngẫu nhiên:
# gitleaks sẽ báo động vì nó trông giống credential thật, và như thế là làm
# nhiễu đúng cái công cụ dùng để bắt secret thật. Đây là giá trị của test,
# không bao giờ dùng ở staging/production.
os.environ["STAFF_API_KEYS"] = "staff-key-for-tests-only"
# Bật rate limit nhưng đặt trần cao để test thường không bị chặn;
# test riêng cho rate limit sẽ tự hạ trần.
os.environ["RATE_LIMIT_ENABLED"] = "true"
os.environ["RATE_LIMIT_LEADS_PER_WINDOW"] = "1000"
os.environ["RATE_LIMIT_WINDOW_SECONDS"] = "60"
os.environ["TURNSTILE_SECRET_KEY"] = ""
os.environ["TURNSTILE_REQUIRED"] = "false"
os.environ["TRUST_PROXY_HEADERS"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"
# G08: giới hạn Host header (TestClient dùng Host: testserver)
os.environ["ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"

# --------------------------------------------------------------------------
# Từ đây mới được import app.*
# --------------------------------------------------------------------------
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import REPO_ROOT, settings  # noqa: E402
from app.main import create_app  # noqa: E402

STAFF_KEY = "staff-key-for-tests-only"

ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def alembic_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def reset_public_schema(url: str) -> None:
    """Xoá sạch schema public để mỗi phiên test bắt đầu từ số 0."""
    engine = create_engine(url, isolation_level="AUTOCOMMIT", future=True)
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def load_initial_migration():
    """Nạp module migration 0001 để dùng CHUNG dữ liệu seed.

    Tên file bắt đầu bằng chữ số nên không import thường được; dùng importlib.
    Dùng chung hàm `seed_rows()` bảo đảm test và migration không lệch nhau.
    """
    import importlib.util

    path = REPO_ROOT / "migrations" / "versions" / "0001_initial.py"
    spec = importlib.util.spec_from_file_location("vipphone_migration_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_catalog_migration():
    """Nạp module migration 0007 để dùng CHUNG danh sách 10 category (G14).

    Cùng lý do với `load_initial_migration`: nếu test tự chép lại danh sách
    category thì hai bản sẽ lệch nhau, và bản test sẽ là bản nói dối.
    """
    import importlib.util

    path = REPO_ROOT / "migrations" / "versions" / "0007_product_catalog.py"
    spec = importlib.util.spec_from_file_location("vipphone_migration_0007", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INITIAL_MIGRATION = load_initial_migration()
CATALOG_MIGRATION = load_catalog_migration()


@pytest.fixture(scope="session")
def database_url() -> str:
    return TEST_DATABASE_URL


@pytest.fixture(scope="session", autouse=True)
def migrated_database(database_url: str) -> str:
    """Dựng schema bằng CHÍNH migration của dự án (không `create_all`)."""
    reset_public_schema(database_url)
    command.upgrade(alembic_config(database_url), "head")
    return database_url


@pytest.fixture(scope="session")
def engine(database_url: str, migrated_database: str):
    eng = create_engine(database_url, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean_tables(engine, migrated_database: str) -> None:
    """Trả database về trạng thái chuẩn trước MỖI test.

    Phải dựng lại CẢ danh mục `iphone_models`, không chỉ xoá lead: có test cố
    ý tắt một model hoặc thêm model mới, và nếu không dựng lại thì các test
    sau sẽ hỏng vì lý do chẳng liên quan gì tới chúng.
    """
    with engine.begin() as conn:
        # G14: dọn CẢ bảng danh mục sản phẩm. Không dọn thì sản phẩm của test này
        # rò sang test khác, và `total` ở các test phân trang sẽ sai một cách khó hiểu.
        conn.execute(
            text(
                "TRUNCATE TABLE audit_events, leads, device_compatibility, "
                "product_variants, products, categories RESTART IDENTITY CASCADE"
            )
        )
        conn.execute(text("TRUNCATE TABLE iphone_models RESTART IDENTITY CASCADE"))
        conn.execute(
            INITIAL_MIGRATION.MODELS_TABLE.insert(),
            INITIAL_MIGRATION.seed_rows(),
        )
        # 10 category lấy TỪ CHÍNH migration 0007 — một nguồn duy nhất.
        conn.execute(
            text(
                "INSERT INTO categories (code, name, sort_order, active) "
                "VALUES (:code, :name, :sort_order, true)"
            ),
            [
                {"code": code, "name": name, "sort_order": index}
                for index, (code, name) in enumerate(CATALOG_MIGRATION.SEED_CATEGORIES)
            ],
        )


@pytest.fixture
def db(engine) -> Session:
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def staff_headers() -> dict[str, str]:
    return {"X-Staff-Key": STAFF_KEY}


@pytest.fixture
def valid_lead_payload() -> dict:
    return {
        "full_name": "Nguyễn Văn A",
        "phone": "0912345678",
        "iphone_model": "iphone-16-pro-max",
        "case_color": "Đen",
        "company_name": "Công ty TNHH ABC",
        "bni_chapter": "BNI Growth",
        "referrer_name": "Trần Thị B",
        "source": "bni",
        "ref": "BNI123",
        "consent": True,
    }
