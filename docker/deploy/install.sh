#!/usr/bin/env bash
# install.sh — one-time installer for the slim-side deploy infrastructure.
#
# Run this ONCE on slim as the user (with sudo) to install the deploy.sh
# and rollback.sh scripts at /opt/wize73/, plus the docker compose file.
#
#     sudo bash docker/deploy/install.sh
#
# Subsequent deploys are handled by the deploy-on-main GH workflow which
# SSHes to slim and runs /opt/wize73/deploy.sh <sha>. The user only needs
# to run install.sh once at first setup time, and again whenever a
# CODEOWNERS-locked change to the deploy infrastructure needs to be
# rolled out.

set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: must run as root (use sudo)" >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST_DIR="/opt/wize73"
COMPOSE_DIR="/etc/docker/compose/wize73"

echo "==> creating $DEST_DIR and $COMPOSE_DIR"
install -d -m 0755 "$DEST_DIR"
install -d -m 0755 "$COMPOSE_DIR"

echo "==> installing deploy.sh and rollback.sh to $DEST_DIR"
install -m 0755 "$REPO_ROOT/docker/deploy/deploy.sh" "$DEST_DIR/deploy.sh"
install -m 0755 "$REPO_ROOT/docker/deploy/rollback.sh" "$DEST_DIR/rollback.sh"

echo "==> installing docker-compose.yml to $COMPOSE_DIR"
install -m 0644 "$REPO_ROOT/docker/compose.example.yml" "$COMPOSE_DIR/docker-compose.yml"

echo "==> installing nftables egress firewall"
install -m 0755 "$REPO_ROOT/docker/firewall/setup.sh" "$DEST_DIR/firewall-setup.sh"
install -m 0644 "$REPO_ROOT/docker/firewall/rules.nft" "$DEST_DIR/firewall-rules.nft"

echo
echo "✓ installed. Next steps:"
echo
echo "  1. Set environment variables in /etc/docker/compose/wize73/.env:"
echo "       OPS_BEARER_TOKEN=<random-32-char-hex>"
echo "       AGENT_PROXY_TOKEN=<random-32-char-hex>"
echo
echo "  2. Apply the firewall rules:"
echo "       sudo $DEST_DIR/firewall-setup.sh"
echo
echo "  3. Pull the latest image and start:"
echo "       cd $COMPOSE_DIR && IMAGE_TAG=latest docker compose up -d"
echo
echo "  4. Verify the public URL:"
echo "       curl https://class.wize73.com/healthz"
echo
echo "  5. From here, the deploy-on-main GH workflow handles all updates"
echo "     automatically. Use $DEST_DIR/rollback.sh for manual rollback."
