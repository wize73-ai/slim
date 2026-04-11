################################################################################
# Agent inference proxy.
#
# CI's only path to guapo. Listens on the internal docker network plus a
# host-bound port that cloudflared on slim routes to from the public
# tunnel (path-based ingress under class.wize73.com/agents-llm).
#
# Same hardening as the app container.
################################################################################

FROM --platform=linux/amd64 python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 proxy \
    && useradd --system --uid 1000 --gid proxy --home-dir /app --shell /usr/sbin/nologin proxy

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY --chown=proxy:proxy server.py ./

USER proxy:proxy

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD curl --fail --silent --max-time 3 http://127.0.0.1:8080/healthz || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
