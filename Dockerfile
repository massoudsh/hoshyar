# syntax=docker/dockerfile:1

FROM python:3.12-slim

# Unbuffered output so JSON logs reach the container runtime immediately.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    HOSHYAR_HOST=0.0.0.0 \
    HOSHYAR_PORT=8000 \
    HOSHYAR_DATABASE_PATH=/data/hoshyar.sqlite3

WORKDIR /app

# The app has no third-party dependencies, so nothing is pip-installed.
COPY hoshyar/ /app/hoshyar/
COPY frontend/ /app/frontend/

RUN mkdir -p /data && chown -R 10001:10001 /data

# Unprivileged user: the process never needs to write outside /data.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hoshyar \
    && chown -R 10001:10001 /app
USER 10001

VOLUME ["/data"]
EXPOSE 8000

# /health is unauthenticated, so it is a safe liveness probe.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"]

ENTRYPOINT ["python", "-m", "hoshyar.server"]
