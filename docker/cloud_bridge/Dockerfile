FROM python:3.11-slim

LABEL maintainer="CineOS Team"
LABEL description="CineOS Cloud Bridge — dispatches heavy AI to free cloud services"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SERVICE_NAME=cloud_bridge \
    BRIDGE_PORT=8600 \
    LOG_LEVEL=INFO \
    TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r cineos && useradd -r -g cineos -d /app -s /sbin/nologin cineos

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=cineos:cineos . .

RUN mkdir -p /app/logs && chown -R cineos:cineos /app/logs

USER cineos

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${BRIDGE_PORT:-8600}/health || exit 1

EXPOSE ${BRIDGE_PORT:-8600}

CMD ["python", "-m", "workers.cloud_bridge"]
