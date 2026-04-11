#!/usr/bin/env bash
# Tail nftables drop log entries and forward them to the ops dashboard.
#
# Watches journald for "wize73-drop:" prefix entries (from rules.nft's
# log statement), parses each into an event, and POSTs it to the
# instructor ops dashboard at https://class.wize73.com/ops/events with
# severity=critical.
#
# Run on slim as a systemd service. The service unit file is in
# docker/firewall/audit_drops.service (or installed by deploy.sh).
#
# Required env:
#     OPS_INGEST_TOKEN — bearer token for the ops dashboard ingest endpoint
#     OPS_URL          — base URL of the ops dashboard (default class.wize73.com/ops)

set -euo pipefail

OPS_URL="${OPS_URL:-https://class.wize73.com/ops}"
INGEST_ENDPOINT="$OPS_URL/events"

if [[ -z "${OPS_INGEST_TOKEN:-}" ]]; then
    echo "ERROR: OPS_INGEST_TOKEN env var not set" >&2
    exit 1
fi

post_event() {
    local summary="$1"
    local payload="$2"
    curl -s -X POST "$INGEST_ENDPOINT" \
        -H "Authorization: Bearer $OPS_INGEST_TOKEN" \
        -H "Content-Type: application/json" \
        --max-time 5 \
        -d "{
            \"severity\": \"critical\",
            \"source\": \"firewall\",
            \"kind\": \"drop\",
            \"summary\": $(printf '%s' "$summary" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))'),
            \"payload\": $payload
        }" >/dev/null || echo "WARN: failed to post event to $INGEST_ENDPOINT" >&2
}

echo "==> tailing journald for wize73-drop entries..."

# -f follow, -k kernel only (nftables logs to kern.log), --since now
journalctl -f -k --since "now" -o cat 2>/dev/null \
    | grep --line-buffered "wize73-drop:" \
    | while IFS= read -r line; do
        # Extract dst IP and port if present.
        dst=$(echo "$line" | grep -oE 'DST=[0-9.]+' | head -1 | cut -d= -f2)
        port=$(echo "$line" | grep -oE 'DPT=[0-9]+' | head -1 | cut -d= -f2)
        proto=$(echo "$line" | grep -oE 'PROTO=[A-Z]+' | head -1 | cut -d= -f2)

        summary="egress to ${dst:-?}:${port:-?} (${proto:-?}) blocked"
        payload=$(printf '{"dst":"%s","port":"%s","proto":"%s"}' "${dst:-}" "${port:-}" "${proto:-}")

        echo "drop: $summary"
        post_event "$summary" "$payload"
    done
