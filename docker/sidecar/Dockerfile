################################################################################
# Slim host-stats sidecar.
#
# Tiny container that runs alongside the app on slim. Exposes a single
# /stats endpoint on the internal docker network only. The /proc, /sys,
# and /etc/os-release mounts are added at runtime by docker compose with
# read-only flags.
#
# Same hardening philosophy as the app container — non-root, minimal
# attack surface — but read-only rootfs is NOT enabled in compose for
# this container because psutil needs to write to /tmp for some
# operations.
################################################################################

FROM --platform=linux/amd64 python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 sidecar \
    && useradd --system --uid 1000 --gid sidecar --home-dir /app --shell /usr/sbin/nologin sidecar

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY --chown=sidecar:sidecar server.py ./

USER sidecar:sidecar

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD curl --fail --silent --max-time 3 http://127.0.0.1:8080/healthz || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
