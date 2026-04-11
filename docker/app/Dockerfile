################################################################################
# Dockerfile for the wize73 class chatbot app container.
#
# Base: python:3.12-slim (linux/amd64, matches slim's architecture).
# Two-stage build: builder installs deps in a venv, runtime copies the venv
# and code, drops to a non-root user.
#
# Hardening flags (read-only rootfs, cap_drop ALL, no host mounts) live in
# the compose file at runtime, not in this Dockerfile, since they're
# orchestration concerns.
################################################################################

# ─── Stage 1: builder ───────────────────────────────────────────────────────
FROM --platform=linux/amd64 python:3.12-slim AS builder

# Build deps. Removed in final stage by virtue of multi-stage.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create the virtualenv at a known location for the runtime stage to copy.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install pinned dependencies from the locked manifest.
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# ─── Stage 2: runtime ───────────────────────────────────────────────────────
FROM --platform=linux/amd64 python:3.12-slim AS runtime

# Minimal runtime deps. curl is used by the HEALTHCHECK only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --home-dir /app --shell /usr/sbin/nologin app

# Copy the prebuilt venv from the builder stage. Owned by the app user
# so the read-only rootfs in compose still allows reads.
COPY --from=builder --chown=app:app /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy the application code. Excluded by .dockerignore: tests, .venv,
# .git, docs, node_modules, anything not needed at runtime.
COPY --chown=app:app core/ ./core/
COPY --chown=app:app app/ ./app/
COPY --chown=app:app requirements.txt ./

USER app:app

# Cloudflared on slim ingresses traffic to localhost:8080. The compose
# port mapping binds this container's :8080 to 127.0.0.1:8080 on the host.
EXPOSE 8080

# Health probe used both by docker's HEALTHCHECK and by deploy.sh's
# blue/green wait loop. Three retries over 30 seconds covers slow startup.
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD curl --fail --silent --max-time 3 http://127.0.0.1:8080/healthz || exit 1

# uvicorn directly — no gunicorn/multiple workers because the metrics
# ring buffer is in-process state and would diverge across workers.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "1", \
     "--access-log", \
     "--no-server-header", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "127.0.0.1"]
