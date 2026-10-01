# VIP PHONE — lệnh thường dùng
#
# Python 3.12. Trên máy đã có venv ở .venv/ (đã gitignore).

PYTHON ?= .venv/bin/python
PIP    ?= .venv/bin/pip

.PHONY: help venv install install-dev run migrate migrate-down migrate-check \
        revision lint lint-fix test test-unit test-integration test-e2e \
        secret-scan check clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

venv: ## Tạo virtualenv Python 3.12
	python3.12 -m venv .venv

install: ## Cài dependency chạy thật
	$(PIP) install -r requirements.txt

install-dev: ## Cài dependency đầy đủ (gồm test, lint)
	$(PIP) install -r requirements-dev.txt
	.venv/bin/playwright install chromium

run: ## Chạy server dev
	.venv/bin/uvicorn app.main:app --reload --port 8000

migrate: ## Áp dụng migration lên head
	.venv/bin/alembic upgrade head

migrate-down: ## Lùi một bước migration
	.venv/bin/alembic downgrade -1

migrate-check: ## Kiểm tra migration head khớp schema thật
	.venv/bin/alembic upgrade head
	.venv/bin/alembic check

revision: ## Tạo migration mới: make revision m="mô tả"
	.venv/bin/alembic revision --autogenerate -m "$(m)"

lint: ## Chạy ruff
	.venv/bin/ruff check app tests tests_e2e migrations
	.venv/bin/ruff format --check app tests tests_e2e migrations

lint-fix: ## Tự sửa lỗi ruff
	.venv/bin/ruff check --fix app tests tests_e2e migrations
	.venv/bin/ruff format app tests tests_e2e migrations

test: ## Chạy toàn bộ test backend
	.venv/bin/pytest -q

test-unit: ## Chỉ unit test (không cần database)
	.venv/bin/pytest -q -m "not integration"

test-integration: ## Chỉ integration test (cần PostgreSQL)
	.venv/bin/pytest -q -m integration

test-e2e: ## Test E2E trình duyệt thật (cần Chromium của Playwright)
	$(PYTHON) -m pytest -q tests_e2e

secret-scan: ## Quét secret toàn bộ lịch sử git
	gitleaks git --no-banner --redact --exit-code 1

check: lint test secret-scan ## Chạy toàn bộ kiểm tra trước khi mở PR

clean: ## Dọn file tạm
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
