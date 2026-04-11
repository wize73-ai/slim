#!/usr/bin/env bash
# /opt/wize73/rollback.sh — manual one-command rollback to a previous image.
#
# Lives ON slim at /opt/wize73/rollback.sh, mode 0755. The copy in
# docker/deploy/rollback.sh is a REFERENCE — install once, CI can't
# modify it.
#
# Usage:
#     rollback.sh                  # roll back to the most recent :previous tag
#     rollback.sh sha-abc123       # roll back to a specific commit SHA
#     rollback.sh --list           # show available tags
#
# Auto-rollback on health-check failure already happens during deploy.sh
# (within 30 seconds of a bad deploy). Use this script for the cases the
# auto-rollback can't handle: stuck deploys, behavioral regressions that
# don't trip the health check, "I want to go back further than just one
# commit".

set -euo pipefail

REGISTRY="ghcr.io/wize73-ai/slim/app"
COMPOSE_DIR="/etc/docker/compose/wize73"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }
die() { log "ERROR: $*"; exit 1; }

list_tags() {
    log "available local tags for $REGISTRY:"
    docker images "$REGISTRY" --format '  {{.Tag}}\t{{.CreatedSince}}\t{{.Size}}' \
        | sort -u
}

if [[ "${1:-}" == "--list" || "${1:-}" == "-l" ]]; then
    list_tags
    exit 0
fi

TARGET_TAG="${1:-previous}"

# Sanity check the tag exists locally before doing anything destructive.
if ! docker image inspect "$REGISTRY:$TARGET_TAG" &>/dev/null; then
    log "tag $REGISTRY:$TARGET_TAG not found locally"
    list_tags
    die "rollback aborted"
fi

# Confirm if running interactively (skip if stdin is not a tty, e.g. ssh).
if [[ -t 0 ]]; then
    read -r -p "Roll back wize73-app to $TARGET_TAG? [y/N] " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        die "cancelled"
    fi
fi

CURRENT_IMAGE=$(docker inspect --format='{{.Config.Image}}' wize73-app 2>/dev/null || echo "<none>")
log "current image: $CURRENT_IMAGE"
log "rolling to:    $REGISTRY:$TARGET_TAG"

cd "$COMPOSE_DIR"
export IMAGE_TAG="$TARGET_TAG"

if ! docker compose up -d --force-recreate --no-deps app; then
    die "docker compose up failed during rollback"
fi

log "==> waiting for /healthz on rolled-back image"
elapsed=0
while [[ $elapsed -lt 30 ]]; do
    if curl -fsS --max-time 2 http://127.0.0.1:8080/healthz &>/dev/null; then
        log "✓ /healthz responding — rollback complete"
        log "  current image: $REGISTRY:$TARGET_TAG"
        exit 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

die "health check failed after rollback — system is in a bad state, intervene manually"
