FROM python:3.11-slim

LABEL maintainer="CineOS Team"
LABEL description="CineOS lightweight worker service (cloud-first)"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl libpq-dev gcc g++ libffi-dev libssl-dev \
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
