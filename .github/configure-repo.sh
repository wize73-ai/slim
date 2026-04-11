#!/usr/bin/env bash
# Configure the wize73-ai/slim repository: branch protection rules and
# the repository secrets the workflows need.
#
# Run this ONCE after the initial setup. Re-running is idempotent (it
# overwrites the existing protection rules with the same shape and
# silently no-ops on identical secrets).
#
# Requires:
#   - gh CLI installed and authenticated (`gh auth status`)
#   - You must be a repo admin
#
# Usage:
#     bash .github/configure-repo.sh                  # apply everything
#     bash .github/configure-repo.sh --branch-only    # just branch protection
#     bash .github/configure-repo.sh --secrets-only   # just secrets
#     bash .github/configure-repo.sh --dry-run        # show what would happen

set -euo pipefail

REPO="wize73-ai/slim"
BRANCH="main"

# ────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ────────────────────────────────────────────────────────────────────────────

DO_BRANCH=1
DO_SECRETS=1
DRY_RUN=0

for arg in "$@"; do
    case "$arg" in
        --branch-only)   DO_SECRETS=0 ;;
        --secrets-only)  DO_BRANCH=0 ;;
        --dry-run)       DRY_RUN=1 ;;
        -h|--help)
            head -25 "$0"
            exit 0
            ;;
        *)
            echo "unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

run() {
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "    [dry-run] $*"
    else
        "$@"
    fi
}

# ────────────────────────────────────────────────────────────────────────────
# Pre-flight checks
# ────────────────────────────────────────────────────────────────────────────

if ! command -v gh &>/dev/null; then
    echo "ERROR: gh CLI not installed — https://cli.github.com/" >&2
    exit 1
fi

if ! gh auth status &>/dev/null; then
    echo "ERROR: gh not authenticated. Run: gh auth login" >&2
    exit 1
fi

echo "==> configuring $REPO (branch=$DO_BRANCH secrets=$DO_SECRETS dry_run=$DRY_RUN)"

# ────────────────────────────────────────────────────────────────────────────
# Branch protection on main
# ────────────────────────────────────────────────────────────────────────────

if [[ $DO_BRANCH -eq 1 ]]; then
    echo
    echo "==> setting branch protection on $BRANCH"

    # Required status checks — every PR agent + the deploy workflow.
    # These names come from the `name:` field of each workflow file.
    cat > /tmp/wize73-protection.json <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "checks": [
      {"context": "secrets-scan"},
      {"context": "code-quality"},
      {"context": "red-team"},
      {"context": "blue-team"},
      {"context": "classroom-safety"},
      {"context": "version-discipline"},
      {"context": "build-and-smoke"},
      {"context": "slop-and-scope"},
      {"context": "malicious-code-review"}
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "required_approving_review_count": 0,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": true,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": false
}
JSON

    run gh api \
        --method PUT \
        -H "Accept: application/vnd.github+json" \
        "repos/$REPO/branches/$BRANCH/protection" \
        --input /tmp/wize73-protection.json

    rm -f /tmp/wize73-protection.json
    echo "    ✓ branch protection applied"
fi

# ────────────────────────────────────────────────────────────────────────────
# Repository secrets
# ────────────────────────────────────────────────────────────────────────────

if [[ $DO_SECRETS -eq 1 ]]; then
    echo
    echo "==> setting repository secrets"

    secrets_to_set=(
        # Tailscale OAuth client for the deploy workflow
        TAILSCALE_OAUTH_CLIENT_ID
        TAILSCALE_OAUTH_SECRET

        # Agent inference proxy token (used by LLM-based agents)
        AGENT_PROXY_TOKEN

        # Optional: agent proxy URL override (defaults to class.wize73.com/agents-llm)
        AGENT_PROXY_URL
    )

    for name in "${secrets_to_set[@]}"; do
        if gh secret list -R "$REPO" 2>/dev/null | grep -q "^$name"; then
            echo "    ✓ $name already set (use 'gh secret set $name' to update)"
        else
            echo
            echo "    $name is not set yet."
            if [[ $DRY_RUN -eq 0 ]]; then
                read -r -p "    Enter value (or press Enter to skip): " value
                if [[ -n "$value" ]]; then
                    echo -n "$value" | gh secret set "$name" -R "$REPO"
                    echo "    ✓ $name set"
                else
                    echo "    skipped (set later with: gh secret set $name -R $REPO)"
                fi
            fi
        fi
    done
fi

echo
echo "✓ done"
echo
echo "Verify with:"
echo "    gh api repos/$REPO/branches/$BRANCH/protection | jq ."
echo "    gh secret list -R $REPO"
