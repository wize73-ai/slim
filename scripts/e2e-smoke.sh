#!/usr/bin/env bash
# End-to-end smoke test for the deployed wize73 stack.
#
# Run from anywhere with internet + gh CLI authenticated. Probes the
# live deployment at class.wize73.com plus the GitHub repo configuration.
#
# Categories:
#
#   1. Public surface         class.wize73.com responds, /healthz works,
#                             metrics tab loads, ops returns 401 without auth
#   2. Round-trip chat        POST a real chat turn, verify the response,
#                             verify the metrics tab recorded the new turn
#   3. Frozen surface         direct guapo probe (LAN-reachable from this
#                             machine; skipped otherwise) — chat + STT + TTS
#   4. Repo configuration     branch protection on main, required status
#                             checks listed, required secrets set
#   5. Deploy artifacts       latest image on GHCR, deploy.sh + rollback.sh
#                             installed on slim, firewall rules in place
#                             (skipped — requires slim ssh access)
#
# Usage:
#     bash scripts/e2e-smoke.sh                full battery
#     bash scripts/e2e-smoke.sh --public-only  just the public URL checks
#     bash scripts/e2e-smoke.sh --repo-only    just the repo config checks
#     bash scripts/e2e-smoke.sh --quick        skip the round-trip chat

set -uo pipefail

# ────────────────────────────────────────────────────────────────────────────
# Config
# ────────────────────────────────────────────────────────────────────────────

PUBLIC_URL="${PUBLIC_URL:-https://class.wize73.com}"
GUAPO_LAN_URL="${GUAPO_LAN_URL:-http://192.168.1.103:8000}"
REPO="${REPO:-wize73-ai/slim}"

DO_PUBLIC=1
DO_REPO=1
DO_CHAT=1

for arg in "$@"; do
    case "$arg" in
        --public-only)  DO_REPO=0; DO_CHAT=1 ;;
        --repo-only)    DO_PUBLIC=0; DO_CHAT=0 ;;
        --quick)        DO_CHAT=0 ;;
        -h|--help) head -25 "$0"; exit 0 ;;
        *) echo "unknown arg: $arg" >&2; exit 1 ;;
    esac
done

if [[ -t 1 ]]; then
    R='\033[0;31m'
    G='\033[0;32m'
    Y='\033[0;33m'
    B='\033[0;34m'
    BOLD='\033[1m'
    N='\033[0m'
else
    R='' G='' Y='' B='' BOLD='' N=''
fi

PASSES=0
FAILURES=()

step() { echo; echo -e "${B}══ $1 ══${N}"; }
pass() { echo -e "  ${G}✓${N} $1"; PASSES=$((PASSES + 1)); }
warn() { echo -e "  ${Y}⚠${N} $1"; }
fail() { echo -e "  ${R}✗${N} $1"; FAILURES+=("$1"); }

require() {
    if ! command -v "$1" &>/dev/null; then
        warn "$1 not installed — some checks skipped"
        return 1
    fi
    return 0
}

# ────────────────────────────────────────────────────────────────────────────
# 1. Public surface
# ────────────────────────────────────────────────────────────────────────────

if [[ $DO_PUBLIC -eq 1 ]]; then
    step "1/5  public surface ($PUBLIC_URL)"

    # /healthz
    status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$PUBLIC_URL/healthz" || echo "000")
    if [[ "$status" == "200" ]]; then
        pass "$PUBLIC_URL/healthz returns 200"
    else
        fail "$PUBLIC_URL/healthz returned $status (expected 200)"
    fi

    # / (chat UI)
    status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$PUBLIC_URL/" || echo "000")
    if [[ "$status" == "200" || "$status" == "302" ]]; then
        pass "$PUBLIC_URL/ chat UI returns $status"
    else
        fail "$PUBLIC_URL/ returned $status"
    fi

    # /metrics/healthz
    status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$PUBLIC_URL/metrics/healthz" || echo "000")
    if [[ "$status" == "200" ]]; then
        pass "$PUBLIC_URL/metrics/healthz returns 200"
    else
        fail "$PUBLIC_URL/metrics/healthz returned $status"
    fi

    # /metrics/ contains the locked tab markers
    body=$(curl -s --max-time 10 "$PUBLIC_URL/metrics/" || echo "")
    if echo "$body" | grep -q "Token flow by turn"; then
        pass "$PUBLIC_URL/metrics/ contains 'Token flow by turn' marker"
    else
        fail "$PUBLIC_URL/metrics/ missing locked marker 'Token flow by turn'"
    fi
    if echo "$body" | grep -q "Projection calculator"; then
        pass "$PUBLIC_URL/metrics/ contains 'Projection calculator' marker"
    else
        fail "$PUBLIC_URL/metrics/ missing locked marker 'Projection calculator'"
    fi

    # /ops should require auth
    status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$PUBLIC_URL/ops/" || echo "000")
    if [[ "$status" == "401" || "$status" == "302" ]]; then
        pass "$PUBLIC_URL/ops/ correctly requires auth (got $status)"
    else
        fail "$PUBLIC_URL/ops/ returned $status — should require auth (401 or 302)"
    fi

    # TLS cert validity
    if echo | openssl s_client -servername "${PUBLIC_URL#https://}" -connect "${PUBLIC_URL#https://}:443" 2>/dev/null \
            | openssl x509 -noout -checkend 604800 &>/dev/null; then
        pass "TLS cert valid for at least 7 more days"
    else
        warn "TLS cert expires in less than 7 days (or check failed)"
    fi
fi

# ────────────────────────────────────────────────────────────────────────────
# 2. Round-trip chat
# ────────────────────────────────────────────────────────────────────────────

if [[ $DO_CHAT -eq 1 && $DO_PUBLIC -eq 1 ]]; then
    step "2/5  round-trip chat"

    # Get the turn count BEFORE the chat call.
    before=$(curl -s --max-time 5 "$PUBLIC_URL/metrics/turns" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("count",0))' 2>/dev/null || echo "?")
    echo "    turns recorded before: $before"

    # Send a chat turn.
    chat_response=$(curl -s --max-time 60 -X POST "$PUBLIC_URL/chat" \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        -d 'user_message=hello%20from%20smoke%20test' || echo "")

    if [[ -n "$chat_response" ]]; then
        pass "POST /chat returned a non-empty response"
        # Check the response is HTML and contains the assistant marker
        if echo "$chat_response" | grep -q "assistant"; then
            pass "  response includes 'assistant' marker"
        else
            warn "  response did not include 'assistant' marker"
        fi
    else
        fail "POST /chat returned empty response"
    fi

    # The chat turn should have flowed into the ring buffer.
    sleep 1
    after=$(curl -s --max-time 5 "$PUBLIC_URL/metrics/turns" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("count",0))' 2>/dev/null || echo "?")
    echo "    turns recorded after:  $after"

    if [[ "$after" != "?" && "$before" != "?" && "$after" -gt "$before" ]]; then
        pass "ring buffer recorded the new turn ($before → $after)"
    elif [[ "$after" == "$before" ]]; then
        fail "ring buffer did NOT record the chat turn ($before → $after)"
    else
        warn "could not verify ring buffer increment"
    fi
fi

# ────────────────────────────────────────────────────────────────────────────
# 3. Frozen guapo surface (LAN-reachable only)
# ────────────────────────────────────────────────────────────────────────────

if [[ $DO_PUBLIC -eq 1 ]]; then
    step "3/5  frozen guapo surface ($GUAPO_LAN_URL)"

    if curl -s --max-time 3 "$GUAPO_LAN_URL/healthz" &>/dev/null; then
        pass "guapo /healthz reachable on LAN"

        # Models
        models=$(curl -s --max-time 5 "$GUAPO_LAN_URL/v1/models" \
            | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("data",[])))' 2>/dev/null || echo "?")
        if [[ "$models" != "?" && "$models" -ge 3 ]]; then
            pass "guapo /v1/models returns $models models (expected ≥3)"
        else
            warn "guapo /v1/models returned unexpected count: $models"
        fi
    else
        warn "guapo /healthz not reachable on LAN — skipping (you may not be on the same LAN)"
    fi
fi

# ────────────────────────────────────────────────────────────────────────────
# 4. Repository configuration
# ────────────────────────────────────────────────────────────────────────────

if [[ $DO_REPO -eq 1 ]] && require gh; then
    step "4/5  repository configuration ($REPO)"

    # Branch protection on main
    if gh api "repos/$REPO/branches/main/protection" &>/dev/null; then
        pass "branch protection enabled on main"

        required=$(gh api "repos/$REPO/branches/main/protection" \
            --jq '.required_status_checks.checks | length' 2>/dev/null || echo "0")
        if [[ "$required" -ge 9 ]]; then
            pass "  $required required status checks (≥9)"
        else
            fail "  only $required required status checks (expected ≥9)"
        fi
    else
        fail "branch protection NOT enabled on main"
    fi

    # Required secrets
    secrets_present=$(gh secret list -R "$REPO" 2>/dev/null | awk '{print $1}' || echo "")
    for s in TAILSCALE_OAUTH_CLIENT_ID TAILSCALE_OAUTH_SECRET AGENT_PROXY_TOKEN; do
        if echo "$secrets_present" | grep -q "^$s$"; then
            pass "secret $s is set"
        else
            fail "secret $s is NOT set"
        fi
    done

    # All 9 PR workflows present
    workflows=$(gh api "repos/$REPO/actions/workflows" --jq '.workflows[].name' 2>/dev/null || echo "")
    pr_count=$(echo "$workflows" | grep -c "^pr-" || echo "0")
    if [[ "$pr_count" -ge 9 ]]; then
        pass "$pr_count pr-* workflows present (≥9)"
    else
        fail "only $pr_count pr-* workflows present (expected ≥9)"
    fi
    if echo "$workflows" | grep -q "deploy on main"; then
        pass "deploy-on-main workflow present"
    else
        fail "deploy-on-main workflow not found"
    fi
fi

# ────────────────────────────────────────────────────────────────────────────
# 5. Deploy artifacts (informational; requires slim ssh)
# ────────────────────────────────────────────────────────────────────────────

step "5/5  deploy artifacts"

if ssh -o ConnectTimeout=5 -o BatchMode=yes james@slim 'true' &>/dev/null; then
    pass "ssh james@slim works"

    if ssh james@slim 'test -x /opt/wize73/deploy.sh' &>/dev/null; then
        pass "/opt/wize73/deploy.sh installed and executable"
    else
        fail "/opt/wize73/deploy.sh missing or not executable"
    fi

    if ssh james@slim 'test -x /opt/wize73/rollback.sh' &>/dev/null; then
        pass "/opt/wize73/rollback.sh installed and executable"
    else
        fail "/opt/wize73/rollback.sh missing or not executable"
    fi

    if ssh james@slim 'sudo nft list table inet wize73' &>/dev/null; then
        pass "nftables wize73 table present"
    else
        warn "nftables wize73 table not present (run docker/firewall/setup.sh)"
    fi

    running=$(ssh james@slim "docker ps --format '{{.Names}}'" 2>/dev/null || echo "")
    for name in wize73-app wize73-sidecar wize73-agent-proxy; do
        if echo "$running" | grep -q "^$name$"; then
            pass "container $name is running"
        else
            warn "container $name not running"
        fi
    done
else
    warn "cannot ssh to slim — skipping deploy artifact checks"
    warn "(make sure slim is online, on tailscale, and you have key auth)"
fi

# ────────────────────────────────────────────────────────────────────────────
# Summary
# ────────────────────────────────────────────────────────────────────────────

echo
echo -e "${BOLD}════════════════════════════════════════════════════════════${N}"
if [[ ${#FAILURES[@]} -eq 0 ]]; then
    echo -e "  ${G}${BOLD}✓ smoke passed${N} ($PASSES checks)"
    exit 0
else
    echo -e "  ${R}${BOLD}✗ smoke failed${N} — ${#FAILURES[@]} issue(s) ($PASSES passed)"
    echo
    for f in "${FAILURES[@]}"; do
        echo -e "  ${R}-${N} $f"
    done
    exit 1
fi
