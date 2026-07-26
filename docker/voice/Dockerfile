FROM python:3.11-slim

LABEL maintainer="CineOS Team"
LABEL description="CineOS Voice/TTS worker — Edge TTS only, no local GPU"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VOICE_OUTPUT_DIR=/voice/output \
    VOICE_CACHE_DIR=/voice/cache \
    WORKER_PORT=8002 \
    REDIS_URL=redis://redis:6379/0 \
    DEFAULT_VOICE=en-US-AriaNeural \
    DEFAULT_RATE=0% \
    DEFAULT_VOLUME=0% \
    DEFAULT_PITCH=+0Hz \
    LOG_LEVEL=INFO

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r cineos && useradd -r -g cineos -d /app -s /sbin/nologin cineos

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=cineos:cineos . .

RUN mkdir -p /voice/output /voice/cache /app/logs && \
    chown -R cineos:cineos /voice /app/logs

USER cineos

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${WORKER_PORT:-8002}/health || exit 1

EXPOSE ${WORKER_PORT:-8002}

CMD ["python", "-m", "uvicorn", "voice_server:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "2"]
