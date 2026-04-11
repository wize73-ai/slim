#!/usr/bin/env bash
# explain-failure.sh — read the latest failed PR check run and explain it.
#
# Uses gh CLI to fetch the failing checks on the current PR (or a
# specified PR), looks each up in a static lookup table of agent names →
# wiki pages → "what this means" explanation, and prints actionable
# guidance.
#
# Usage:
#     ./scripts/explain-failure.sh           explain the current branch's PR
#     ./scripts/explain-failure.sh 42        explain PR #42 explicitly
#     ./scripts/explain-failure.sh --list    list all known agents and what they check

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

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

# ────────────────────────────────────────────────────────────────────────────
# Static lookup: agent name → wiki page → explanation
# ────────────────────────────────────────────────────────────────────────────

agent_explain() {
    case "$1" in
        secrets-scan)
            echo "wiki: 05-Agents-Reference#secrets-scan"
            echo
            echo "What it checks: hardcoded secrets, leaked URLs, anything that"
            echo "would expose guapo's identifiers (URL, IP, model names) to"
            echo "students. Both static rules (gitleaks + semgrep) and an LLM"
            echo "catch-net pass."
            echo
            echo "Common fixes:"
            echo "  - Remove any hardcoded URL or IP from your code"
            echo "  - Use os.environ['OPENAI_BASE_URL'] instead of literal strings"
            echo "  - Remove debug print statements that include the URL"
            echo "  - Don't put guapo's identifiers in comments either"
            ;;
        code-quality)
            echo "wiki: 05-Agents-Reference#code-quality"
            echo
            echo "What it checks: ruff format, ruff check (with the strict ruleset),"
            echo "mypy strict on core/, pytest, interrogate docstring coverage."
            echo
            echo "Common fixes:"
            echo "  - Run \`ruff format .\` to auto-fix formatting"
            echo "  - Run \`ruff check --fix .\` to auto-fix lint issues"
            echo "  - Add type hints to function signatures (parameters AND return)"
            echo "  - Add docstrings to public functions (one-line summary minimum)"
            echo "  - Run \`pytest\` and fix failing tests"
            echo
            echo "Each ruff code that fires has a 'why this matters' explanation"
            echo "in the agent's PR comment — read those, they're educational."
            ;;
        red-team)
            echo "wiki: 05-Agents-Reference#red-team"
            echo
            echo "What it checks: 12 adversarial probes against your built container."
            echo "Probes try to extract guapo's URL, leak the system prompt,"
            echo "jailbreak the persona, and confirm the chatbot still works for"
            echo "intended use."
            echo
            echo "Common fixes:"
            echo "  - Don't override the security preamble in your persona"
            echo "  - Don't write a persona that's so locked-down it refuses"
            echo "    everything (the usability canary will catch that)"
            echo "  - Remember: the security_preamble in core/chat/ runs first"
            echo "    and instructs the model to refuse infrastructure questions"
            ;;
        blue-team)
            echo "wiki: 05-Agents-Reference#blue-team"
            echo
            echo "What it checks: defensive code review — missing error handling"
            echo "on guapo calls, missing input validation, missing fallbacks for"
            echo "the inference server being unavailable."
            echo
            echo "Common fixes:"
            echo "  - Wrap stream_completion() calls in try/except with"
            echo "    UpstreamUnavailable, UpstreamTimeout, ChatError handlers"
            echo "  - Validate user input length and type at the route boundary"
            echo "  - Set explicit timeouts on any httpx call you add"
            echo "  - Make sure your route handlers return SOMETHING even when"
            echo "    inference fails — don't let the user stare at a blank page"
            ;;
        classroom-safety)
            echo "wiki: 05-Agents-Reference#classroom-safety"
            echo
            echo "What it checks: content of new persona / system prompt /"
            echo "few-shot files for age-appropriateness. Profanity, sensitive"
            echo "topics, anything that would get the principal calling."
            echo
            echo "Common fixes:"
            echo "  - Remove profanity from prompt content"
            echo "  - Don't reference real teachers, students, or the school"
            echo "    by name in any persona"
            echo "  - Don't write content that could be mistaken for real"
            echo "    medical, legal, mental health, or financial advice"
            echo
            echo "The strictness level is in core/agents/prompts/classroom_safety_rules.yaml"
            ;;
        version-discipline)
            echo "wiki: 05-Agents-Reference#version-discipline"
            echo
            echo "What it checks: pinned dependencies, locked paths untouched,"
            echo "conventional commit messages, branch up to date with main."
            echo
            echo "Common fixes:"
            echo "  - Use feat:/fix:/docs:/refactor:/test:/chore: in commit subjects"
            echo "  - If you need a new dependency, file an issue tagged needs-dep"
            echo "    instead of editing requirements.txt yourself"
            echo "  - If you edited a CODEOWNERS-locked path, you need an"
            echo "    instructor approval — open the PR description and explain why"
            echo "  - Rebase or merge from main: \`git fetch origin && git rebase origin/main\`"
            ;;
        build-and-smoke)
            echo "wiki: 05-Agents-Reference#build-and-smoke"
            echo
            echo "What it checks: docker build of your branch's image, then runs"
            echo "the container and hits /healthz, /metrics/healthz, /metrics/,"
            echo "/ops/healthz. Verifies the locked metrics tab markers are still"
            echo "present (catches PRs that nuke the locked template)."
            echo
            echo "Common fixes:"
            echo "  - Run \`docker build -f docker/app/Dockerfile .\` locally"
            echo "    and check for syntax errors in your changes"
            echo "  - If /metrics/ markers are missing, you broke a locked"
            echo "    template — the agent will tell you which one"
            echo "  - Run \`./scripts/preflight.sh --full\` to reproduce"
            echo "    locally before pushing"
            ;;
        slop-and-scope)
            echo "wiki: 05-Agents-Reference#slop-and-scope"
            echo
            echo "What it checks: AST-based dead code detection, premature"
            echo "abstractions, hallucinated imports, scope creep (your diff"
            echo "vs. the linked issue's stated scope)."
            echo
            echo "Common fixes:"
            echo "  - Remove any function/class/module you added that nothing"
            echo "    else calls — AI tools love to add 'helper' functions you"
            echo "    don't need"
            echo "  - Remove abstractions with only one consumer"
            echo "  - Make sure your diff matches the linked issue's scope —"
            echo "    if it doesn't, split into two PRs"
            echo "  - Link the PR to its issue with 'Closes #N' in the description"
            ;;
        malicious-code-review)
            echo "wiki: 05-Agents-Reference#malicious-code-review"
            echo
            echo "What it checks: deliberate malicious patterns — exfiltration,"
            echo "backdoors, time bombs, obfuscated payloads, supply-chain"
            echo "additions. Dual-judge LLM review (paranoid + naive-intent)."
            echo
            echo "If you genuinely tripped this and you weren't trying to do"
            echo "anything bad, the most common false positives are:"
            echo "  - Dynamic string construction that looks like URL building"
            echo "  - Reading environment variables that contain TOKEN/KEY/SECRET"
            echo "  - Importing modules that aren't typically used (socket, ctypes)"
            echo
            echo "If you see this on your PR, the instructor has been notified"
            echo "and will reach out. Don't be alarmed — the false-positive"
            echo "rate is intentionally high here."
            ;;
        *)
            echo "Unknown agent: $1"
            echo "Run with --list to see all known agents."
            return 1
            ;;
    esac
}

list_agents() {
    cat <<'EOF'
Known PR agents (run on every pull request):

  1. secrets-scan          gitleaks + semgrep + LLM obfuscation review
  2. code-quality          ruff + mypy + pytest + interrogate + LLM pythonic
  3. red-team              12 adversarial probes against built container
  4. blue-team             defensive code review
  5. classroom-safety      content review of prompt/persona files
  6. version-discipline    pinned deps, locked paths, conventional commits
  7. build-and-smoke       docker build + smoke test (locks metrics tab)
  8. slop-and-scope        AST dead-code + scope-vs-intent
  9. malicious-code-review dual-judge malice scan (paranoid + naive)

Run ./scripts/explain-failure.sh <agent-name> for details on any one.
Or run ./scripts/explain-failure.sh on a PR to read its actual failures.
EOF
}

# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────

if [[ "${1:-}" == "--list" ]]; then
    list_agents
    exit 0
fi

# If the first arg is a known agent name, just print its explanation.
if [[ -n "${1:-}" ]] && agent_explain "$1" 2>/dev/null | head -1 | grep -q "^wiki:"; then
    echo -e "${BOLD}== $1 ==${N}"
    agent_explain "$1"
    exit 0
fi

# Otherwise look up the current PR and read its failed checks.
if ! command -v gh &>/dev/null; then
    echo -e "${R}gh CLI not installed${N}"
    echo "  Install: https://cli.github.com/"
    echo
    echo "Or pass an agent name explicitly:"
    echo "  ./scripts/explain-failure.sh code-quality"
    echo
    list_agents
    exit 1
fi

PR_ARG="${1:-}"
if [[ -z "$PR_ARG" ]]; then
    PR_NUM=$(gh pr view --json number --jq .number 2>/dev/null || true)
    if [[ -z "$PR_NUM" ]]; then
        echo -e "${R}no PR found for current branch${N}"
        echo "  Open a PR first, or pass a PR number explicitly:"
        echo "  ./scripts/explain-failure.sh 42"
        exit 1
    fi
else
    PR_NUM="$PR_ARG"
fi

echo -e "${BOLD}reading failing checks for PR #$PR_NUM...${N}"
failed_checks=$(gh pr checks "$PR_NUM" --json name,state \
    --jq '.[] | select(.state == "FAILURE" or .state == "ERROR") | .name' 2>/dev/null || true)

if [[ -z "$failed_checks" ]]; then
    echo -e "${G}no failing checks on PR #$PR_NUM — you're good${N}"
    exit 0
fi

echo
echo -e "${R}failing checks:${N}"
echo "$failed_checks" | sed 's/^/  - /'
echo

# Extract the agent name from each failing check (workflows are named
# pr-NN-<agent>.yml so the check name is e.g. "pr-02-code-quality").
while IFS= read -r check; do
    [[ -z "$check" ]] && continue
    agent_name=$(echo "$check" | sed -E 's/^pr-[0-9]+-//')
    echo -e "${BOLD}── $check ──${N}"
    if agent_explain "$agent_name" 2>/dev/null; then
        echo
    else
        echo "  (no explanation registered for this check name)"
        echo
    fi
done <<< "$failed_checks"

echo "For more detail, see the full check log:"
echo "  gh pr checks $PR_NUM"
