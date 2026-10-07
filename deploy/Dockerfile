# =============================================================================
# VIP PHONE — ảnh chạy thật
# =============================================================================
# CỐ Ý chỉ cài requirements.txt, KHÔNG cài requirements-dev.txt.
#
# Vì sao điều này quan trọng: lỗi STG-1 (docs/MASTER_STATUS.md §31.2) là
# `httpx` chỉ được khai trong requirements-dev.txt trong khi app/security.py
# import nó ở cấp module. CI cài dev requirements nên LUÔN XANH, còn đường cài
# thật thì chưa từng được đi — ứng dụng không khởi động nổi trên staging.
# Ảnh này đi đúng đường cài thật, nên lỗi đó không thể tái diễn trong im lặng.
# =============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Lớp phụ thuộc đứng riêng để đổi mã nguồn không phải cài lại thư viện.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Chạy bằng user không phải root. Ứng dụng không cần ghi vào đâu trong ảnh.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# --workers 1: đúng một tiến trình, theo ADR-0001 §3.2. Giới hạn tốc độ
# (rate limit) của ứng dụng giữ trạng thái trong bộ nhớ tiến trình, nên nhiều
# worker sẽ làm mỗi worker đếm riêng và giới hạn thành ra lỏng gấp N lần.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
