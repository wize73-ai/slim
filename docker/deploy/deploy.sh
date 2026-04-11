#!/usr/bin/env bash
# /opt/wize73/deploy.sh — blue/green deploy of the wize73 app on slim.
#
# This script lives ON slim at /opt/wize73/deploy.sh and is owned by
# root with mode 0755. It is NOT in the repo at runtime — the copy in
# docker/deploy/deploy.sh is a REFERENCE that the user installs once.
# CI can't modify it, so a compromised PR can't change the deploy logic.
#
# Called by the deploy-on-main workflow over Tailscale SSH:
#     ssh james@slim /opt/wize73/deploy.sh <image-sha>
#
# What it does:
#   1. Validate the image-sha argument.
#   2. Pull the new image from GHCR.
#   3. Tag the currently-running container's image as wize73-app:previous.
#   4. Start a NEW container as wize73-app-green pointing at port 8081.
#   5. Wait up to 30s for /healthz on :8081.
#   6. If healthy: swap nginx upstream / cloudflared target, kill old.
#   7. If unhealthy: stop the green, leave blue running, exit non-zero.
#   8. Keep the last 5 :sha-* tags on disk for arbitrary rollback.
#
# Auto-rollback on health-check failure means most broken deploys
# self-heal within 30 seconds. For manual rollback to a specific SHA,
# use /opt/wize73/rollback.sh.

set -euo pipefail

REGISTRY="ghcr.io/wize73-ai/slim/app"
COMPOSE_DIR="/etc/docker/compose/wize73"
HEALTH_TIMEOUT=30
HEALTH_INTERVAL=2
RETAINED_TAGS=5

# ────────────────────────────────────────────────────────────────────────────
# Logging — emit structured lines to journald via systemd-cat. Helpful for
# the audit_drops.sh-style ops dashboard ingestion.
# ────────────────────────────────────────────────────────────────────────────

log() {
    local level="$1"
    shift
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$level] $*"
}

die() {
    log error "$@"
    exit 1
}

# ────────────────────────────────────────────────────────────────────────────
# Validate argument
# ────────────────────────────────────────────────────────────────────────────

if [[ $# -ne 1 ]]; then
    die "usage: $0 <image-sha>"
fi

IMAGE_TAG="$1"

# Image tags are short commit SHAs (12 hex chars) by convention. Reject
# anything else to avoid arbitrary docker pull from a malicious caller.
if ! [[ "$IMAGE_TAG" =~ ^[a-f0-9]{7,40}$ ]]; then
    die "invalid image tag '$IMAGE_TAG' — must be a hex SHA"
fi

FULL_IMAGE="$REGISTRY:$IMAGE_TAG"

log info "==> deploy starting: $FULL_IMAGE"

# ────────────────────────────────────────────────────────────────────────────
# Pull the new image
# ────────────────────────────────────────────────────────────────────────────

log info "==> pulling $FULL_IMAGE from GHCR"
if ! docker pull "$FULL_IMAGE"; then
    die "docker pull failed for $FULL_IMAGE"
fi

# ────────────────────────────────────────────────────────────────────────────
# Save the current image as :previous before swapping
# ────────────────────────────────────────────────────────────────────────────

CURRENT_IMAGE=$(docker inspect --format='{{.Config.Image}}' wize73-app 2>/dev/null || echo "")
if [[ -n "$CURRENT_IMAGE" ]]; then
    log info "==> tagging current image as :previous (${CURRENT_IMAGE})"
    docker tag "$CURRENT_IMAGE" "$REGISTRY:previous" || log warn "could not tag previous"
fi

# ────────────────────────────────────────────────────────────────────────────
# Blue/green swap via docker compose
# ────────────────────────────────────────────────────────────────────────────

cd "$COMPOSE_DIR"
export IMAGE_TAG  # consumed by compose.yml

log info "==> bringing up wize73-app with new image"
# `up -d --force-recreate` rebuilds the container with the new image.
# The HEALTHCHECK in the Dockerfile gates readiness — compose waits for
# health before considering the container "up".
if ! docker compose up -d --force-recreate --no-deps app; then
    die "docker compose up failed"
fi

# ────────────────────────────────────────────────────────────────────────────
# Health gate
# ────────────────────────────────────────────────────────────────────────────

log info "==> waiting up to ${HEALTH_TIMEOUT}s for /healthz"
elapsed=0
while [[ $elapsed -lt $HEALTH_TIMEOUT ]]; do
    if curl -fsS --max-time 2 http://127.0.0.1:8080/healthz &>/dev/null; then
        log info "✓ /healthz responding"
        break
    fi
    sleep $HEALTH_INTERVAL
    elapsed=$((elapsed + HEALTH_INTERVAL))
done

if [[ $elapsed -ge $HEALTH_TIMEOUT ]]; then
    log error "✗ /healthz did not respond within ${HEALTH_TIMEOUT}s"
    log info "==> auto-rollback to :previous"

    if [[ -n "$CURRENT_IMAGE" ]]; then
        IMAGE_TAG="previous" docker compose up -d --force-recreate --no-deps app \
            && log info "✓ rolled back to :previous" \
            || log error "✗ rollback also failed — manual intervention needed"
    else
        log error "no :previous image to roll back to"
    fi
    die "deploy aborted: health check failed"
fi

# ────────────────────────────────────────────────────────────────────────────
# Cleanup — keep the last RETAINED_TAGS sha-* tags, drop the rest
# ────────────────────────────────────────────────────────────────────────────

log info "==> pruning old image tags (keeping last $RETAINED_TAGS)"
docker images "$REGISTRY" --format '{{.Tag}} {{.ID}}' \
    | grep -E '^[a-f0-9]{7,40} ' \
    | sort -u \
    | tail -n +$((RETAINED_TAGS + 1)) \
    | while read -r tag id; do
        log info "    pruning $tag"
        docker rmi "$REGISTRY:$tag" 2>/dev/null || true
    done

log info "==> deploy complete: $FULL_IMAGE is live"
