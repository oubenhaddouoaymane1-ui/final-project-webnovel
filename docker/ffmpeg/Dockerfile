FROM jrottenberg/ffmpeg:7-alpine

LABEL maintainer="CineOS Team"
LABEL description="CineOS FFmpeg render worker"

ENV RENDER_DIR=/render/output \
    TEMP_DIR=/render/tmp \
    MAX_CONCURRENT_JOBS=2 \
    VIDEO_CODEC=libx264 \
    AUDIO_CODEC=aac \
    DEFAULT_CRF=23 \
    DEFAULT_PRESET=medium \
    WORKER_PORT=8001 \
    REDIS_URL=redis://redis:6379/0

RUN apk add --no-cache \
    bash \
    curl \
    python3 \
    py3-pip \
    jq \
    mediainfo \
    && pip3 install --no-cache-dir --break-system-packages \
    redis \
    fastapi \
    uvicorn[standard] \
    pydantic \
    httpx

RUN addgroup -S cineos && adduser -S cineos -G cineos

RUN mkdir -p /render/output /render/tmp /render/templates /app && \
    chown -R cineos:cineos /render /app

COPY --chown=cineos:cineos entrypoint.sh /app/entrypoint.sh
COPY --chown=cineos:cineos render_server.py /app/render_server.py

RUN chmod +x /app/entrypoint.sh

USER cineos

WORKDIR /app

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${WORKER_PORT:-8001}/health || exit 1

EXPOSE ${WORKER_PORT:-8001}

ENTRYPOINT ["/app/entrypoint.sh"]
