#!/usr/bin/env bash
# Apply the wize73 nftables egress allow-list on slim.
#
# Idempotent — re-running this script safely replaces the existing
# wize73 table without disturbing other tables (Docker, ufw, etc.).
#
# Run on slim with sudo:
#     sudo bash docker/firewall/setup.sh
#
# To survive reboot, ensure nftables-persistent is installed and the
# rules are saved via:
#     sudo apt install nftables nftables-persistent
#     sudo nft list ruleset > /etc/nftables.conf

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES_FILE="$SCRIPT_DIR/rules.nft"

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: must run as root (use sudo)" >&2
    exit 1
fi

if ! command -v nft &>/dev/null; then
    echo "ERROR: nft (nftables) is not installed. Install with: apt install nftables" >&2
    exit 1
fi

if [[ ! -f "$RULES_FILE" ]]; then
    echo "ERROR: rules file not found at $RULES_FILE" >&2
    exit 1
fi

echo "==> deleting existing wize73 table (if any)"
nft delete table inet wize73 2>/dev/null || echo "    (no existing table — fresh install)"

echo "==> applying $RULES_FILE"
nft -f "$RULES_FILE"

echo "==> wize73 table after apply:"
nft list table inet wize73

echo
echo "✓ firewall rules applied. To make them survive reboot, run:"
echo "    sudo nft list ruleset > /etc/nftables.conf"
echo "    sudo systemctl enable nftables"
