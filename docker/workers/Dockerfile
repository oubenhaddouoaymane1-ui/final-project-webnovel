FROM python:3.11-slim

LABEL maintainer="CineOS Team"
LABEL description="CineOS worker service"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WORKER_HOST=0.0.0.0 \
    WORKER_PORT=8000 \
    WORKER_CONCURRENCY=4 \
    DATABASE_URL=postgresql://cineos:cineos_secret@postgres:5432/cineos \
    REDIS_URL=redis://redis:6379/0 \
    LOG_LEVEL=INFO \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    libpq-dev \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    mediainfo \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r cineos && useradd -r -g cineos -d /app -s /sbin/nologin cineos

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=cineos:cineos . .

RUN mkdir -p /app/data /app/logs /app/tmp && \
    chown -R cineos:cineos /app/data /app/logs /app/tmp

USER cineos

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${WORKER_PORT:-8000}/health || exit 1

EXPOSE ${WORKER_PORT:-8000}

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
