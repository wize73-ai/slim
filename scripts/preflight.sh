#!/usr/bin/env bash
# preflight.sh — run every PR agent locally in ~30 seconds before pushing.
#
# This is the single biggest velocity unlock for the class. Students who
# run preflight before every push catch ~95% of agent failures locally
# and never burn a CI cycle on a fixable issue. Habit forming.
#
# What it runs (same tools the GH workflows in .github/workflows/ use):
#
#   1. version-discipline   pinned-deps + locked-paths-guard + commit-msg
#   2. code-quality         ruff format-check + ruff check + mypy + pytest
#   3. secrets-scan         gitleaks + semgrep secrets ruleset
#   4. malicious-code-review semgrep security-audit + bandit + AST scanner
#   5. slop-and-scope       Python AST dead-code + duplication scan
#   6. classroom-safety     regex word-list against new prompt/persona files
#   7. blue-team            grep for missing error handling on guapo calls
#   8. red-team             (skipped locally — needs a built container)
#   9. build-and-smoke      (skipped locally unless --full is passed)
#
# Each section runs in sequence with clear ✓ / ✗ output. The script
# returns 0 if everything passed, non-zero otherwise. The first failure
# is highlighted at the end so you know where to start.
#
# Usage:
#     ./scripts/preflight.sh           quick checks only (~15s)
#     ./scripts/preflight.sh --full    include red-team + smoke (~90s)

set -uo pipefail

# ────────────────────────────────────────────────────────────────────────────
# Config + colors
# ────────────────────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FULL_RUN=0
if [[ "${1:-}" == "--full" ]]; then
    FULL_RUN=1
fi

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

FAILURES=()
START_TIME=$(date +%s)

step() {
    local name="$1"
    echo
    echo -e "${B}══ $name ══${N}"
}

pass() {
    echo -e "  ${G}✓${N} $1"
}

warn() {
    echo -e "  ${Y}⚠${N} $1"
}

fail() {
    local msg="$1"
    echo -e "  ${R}✗${N} $msg"
    FAILURES+=("$msg")
}

require() {
    local cmd="$1"
    local install_hint="${2:-install it}"
    if ! command -v "$cmd" &>/dev/null; then
        warn "$cmd not installed — skipping ($install_hint)"
        return 1
    fi
    return 0
}

# ────────────────────────────────────────────────────────────────────────────
# 1. version-discipline (agent 6)
# ────────────────────────────────────────────────────────────────────────────

step "1/9  version-discipline"

# 1a. requirements.txt entries are pinned (no >=, no *, no git URLs).
if [[ -f requirements.txt ]]; then
    bad=$(grep -nE '^[a-zA-Z]' requirements.txt \
        | grep -vE '==[0-9]' \
        | grep -vE '^[0-9]+:#' || true)
    if [[ -z "$bad" ]]; then
        pass "requirements.txt fully pinned"
    else
        fail "requirements.txt has unpinned lines:"
        echo "$bad" | sed 's/^/      /'
    fi
fi

# 1b. No edits to locked paths in the working tree (compared to main).
if git rev-parse --verify origin/main &>/dev/null; then
    locked_changes=$(git diff origin/main --name-only -- \
        'core/' '.github/' 'docker/' 'docs/' \
        2>/dev/null || true)
    if [[ -z "$locked_changes" ]]; then
        pass "no edits to CODEOWNERS-locked paths"
    else
        warn "edits to locked paths (will need code-owner approval to merge):"
        echo "$locked_changes" | sed 's/^/      /'
    fi
else
    warn "no origin/main to compare against — skipping locked-paths check"
fi

# 1c. Conventional-commit format on the most recent commit.
last_subject=$(git log -1 --pretty=%s 2>/dev/null || true)
if [[ -n "$last_subject" ]]; then
    if echo "$last_subject" | grep -qE '^(feat|fix|docs|refactor|test|chore|style|perf|build|ci|revert)(\(.+\))?: .+'; then
        pass "last commit subject is conventional: \"$last_subject\""
    else
        fail "last commit subject is NOT conventional: \"$last_subject\""
        echo "      expected: feat: ... | fix: ... | docs: ... etc."
    fi
fi

# ────────────────────────────────────────────────────────────────────────────
# 2. code-quality (agent 2) — ruff + mypy + pytest
# ────────────────────────────────────────────────────────────────────────────

step "2/9  code-quality"

if require ruff "pip install ruff"; then
    if ruff format --check . &>/tmp/preflight-ruff-fmt.log; then
        pass "ruff format (no diffs)"
    else
        fail "ruff format would change files (run: ruff format .)"
        head -20 /tmp/preflight-ruff-fmt.log | sed 's/^/      /'
    fi

    if ruff check . &>/tmp/preflight-ruff-check.log; then
        pass "ruff check (no lint issues)"
    else
        fail "ruff check found issues (run: ruff check --fix .)"
        head -30 /tmp/preflight-ruff-check.log | sed 's/^/      /'
    fi
fi

if require mypy "pip install mypy"; then
    if mypy core/ &>/tmp/preflight-mypy.log; then
        pass "mypy strict on core/"
    else
        fail "mypy errors on core/ (run: mypy core/)"
        head -20 /tmp/preflight-mypy.log | sed 's/^/      /'
    fi
fi

if require pytest "pip install pytest"; then
    if pytest -q --tb=line --no-header &>/tmp/preflight-pytest.log; then
        pass "pytest (all tests pass)"
    else
        fail "pytest failures (run: pytest)"
        tail -20 /tmp/preflight-pytest.log | sed 's/^/      /'
    fi
fi

if require interrogate "pip install interrogate"; then
    if interrogate -q core/ &>/dev/null; then
        pass "interrogate (docstring coverage ≥80% on core/)"
    else
        fail "interrogate: docstring coverage below threshold"
    fi
fi

# ────────────────────────────────────────────────────────────────────────────
# 3. secrets-scan (agent 1)
# ────────────────────────────────────────────────────────────────────────────

step "3/9  secrets-scan"

if require gitleaks "https://github.com/gitleaks/gitleaks"; then
    if gitleaks detect --no-banner --redact --exit-code 1 &>/tmp/preflight-gitleaks.log; then
        pass "gitleaks (no secrets in tree)"
    else
        fail "gitleaks found secrets"
        head -30 /tmp/preflight-gitleaks.log | sed 's/^/      /'
    fi
fi

# Custom check: any of guapo's stable identifiers in source code outside
# the locked core/ paths where they're allowed (security_preamble.py
# specifically lists them so the output filter can redact them).
forbidden_patterns='100\.91\.130\.128|192\.168\.1\.103|guapo\.local|/models/phi-4-mini'
forbidden_hits=$(grep -RnE "$forbidden_patterns" \
    --include='*.py' --include='*.html' --include='*.md' --include='*.yaml' --include='*.yml' \
    --exclude-dir=.git \
    --exclude-dir=.gitnexus \
    --exclude-dir=node_modules \
    --exclude-dir=__pycache__ \
    --exclude-dir=tests \
    . 2>/dev/null \
    | grep -v 'core/chat/security.py' \
    | grep -v 'core/chat/client.py' \
    | grep -v 'core/chat/README.md' \
    | grep -v 'core/agents/prompts/' \
    | grep -v 'core/agents/proxy.py' \
    | grep -v 'core/observability/templates/_stats_guapo.html' \
    | grep -v 'docker/' \
    | grep -v '.devcontainer/mock-guapo.py' \
    | grep -v '.github/workflows/' \
    | grep -v 'docs/' \
    | grep -v 'CHANGELOG' \
    || true)
if [[ -z "$forbidden_hits" ]]; then
    pass "no guapo identifiers leaking into student-facing code"
else
    fail "found guapo identifiers outside the allowed locked paths:"
    echo "$forbidden_hits" | head -10 | sed 's/^/      /'
fi

# ────────────────────────────────────────────────────────────────────────────
# 4. malicious-code-review (agent 9)
# ────────────────────────────────────────────────────────────────────────────

step "4/9  malicious-code-review"

if require semgrep "pip install semgrep"; then
    if semgrep --config=p/security-audit --config=p/command-injection \
            --quiet --error \
            --exclude='tests' --exclude='.gitnexus' --exclude='node_modules' \
            app/ 2>/tmp/preflight-semgrep.log; then
        pass "semgrep security-audit on app/ (clean)"
    else
        fail "semgrep flagged something on app/"
        tail -20 /tmp/preflight-semgrep.log | sed 's/^/      /'
    fi
fi

if require bandit "pip install bandit"; then
    if bandit -q -r app/ -x tests 2>/tmp/preflight-bandit.log; then
        pass "bandit on app/ (no high-severity issues)"
    else
        fail "bandit flagged issues on app/"
        head -20 /tmp/preflight-bandit.log | sed 's/^/      /'
    fi
fi

# Quick AST scan for the smell patterns the workflow's full agent does.
python3 - <<'PY' 2>&1
import ast
import sys
from pathlib import Path

danger_calls = {"eval", "exec", "compile", "__import__"}
hits = []

for py in Path("app").rglob("*.py"):
    try:
        tree = ast.parse(py.read_text())
    except SyntaxError as e:
        print(f"  ✗ {py}: {e}")
        sys.exit(1)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in danger_calls:
                hits.append(f"{py}:{node.lineno}: {name}()")

if hits:
    print("  ✗ AST danger-call hits:")
    for h in hits:
        print(f"      {h}")
    sys.exit(1)
else:
    print("  ✓ AST scan clean (no eval/exec/compile/__import__ in app/)")
PY
ast_status=$?
if [[ $ast_status -ne 0 ]]; then
    FAILURES+=("AST danger-call scan failed")
fi

# ────────────────────────────────────────────────────────────────────────────
# 5. slop-and-scope (agent 8) — quick AST dead-code scan
# ────────────────────────────────────────────────────────────────────────────

step "5/9  slop-and-scope"

python3 - <<'PY' 2>&1
import ast
from pathlib import Path

defined: dict[str, str] = {}
referenced: set[str] = set()

for py in Path("app").rglob("*.py"):
    try:
        tree = ast.parse(py.read_text())
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            defined.setdefault(node.name, f"{py}:{node.lineno}")
        elif isinstance(node, ast.AsyncFunctionDef) and not node.name.startswith("_"):
            defined.setdefault(node.name, f"{py}:{node.lineno}")
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)

# Skip framework dunder methods like __init__, __enter__, etc., and common
# fastapi handler names.
ignored = {"home", "chat", "healthz", "main"}
dead = {n: loc for n, loc in defined.items()
        if n not in referenced and n not in ignored}

if dead:
    print(f"  ⚠ {len(dead)} functions defined in app/ with no in-app references:")
    for name, loc in list(dead.items())[:10]:
        print(f"      {loc}: {name}()")
    print("  (these may be FastAPI route handlers — verify before removing)")
else:
    print("  ✓ no obvious dead public functions in app/")
PY

# ────────────────────────────────────────────────────────────────────────────
# 6. classroom-safety (agent 5) — regex word-list on prompt/persona content
# ────────────────────────────────────────────────────────────────────────────

step "6/9  classroom-safety"

# Minimal word list — agent 5 has the full list and the LLM secondary review.
wordlist='\b(fuck|shit|bitch|asshole|cunt|nigger|faggot)\b'
content_hits=$(grep -RinE "$wordlist" \
    --include='*.md' --include='*.yaml' --include='*.yml' --include='*.html' \
    --exclude-dir=.git \
    --exclude-dir=.gitnexus \
    --exclude-dir=node_modules \
    app/personas app/system_prompts app/examples app/templates 2>/dev/null || true)

if [[ -z "$content_hits" ]]; then
    pass "no profanity in app/ prompt content"
else
    fail "profanity found in app/ prompt content:"
    echo "$content_hits" | head -10 | sed 's/^/      /'
fi

# ────────────────────────────────────────────────────────────────────────────
# 7. blue-team (agent 4) — quick grep for missing error handling
# ────────────────────────────────────────────────────────────────────────────

step "7/9  blue-team"

# Look for `await client.` or `httpx.` or `stream_completion` calls in app/
# that aren't inside a try block. This is a heuristic, not a real AST scan,
# but catches the most common AI-generated unhandled-call pattern.
unwrapped=$(python3 - 2>&1 <<'PY'
import ast
from pathlib import Path

unwrapped: list[str] = []

DANGER = {
    "stream_completion",
    "build_request",
    "make_client",
}

class Visitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.try_depth = 0

    def visit_Try(self, node: ast.Try) -> None:
        self.try_depth += 1
        self.generic_visit(node)
        self.try_depth -= 1

    def visit_AsyncFunctionDef(self, node) -> None:
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name in DANGER and self.try_depth == 0:
            unwrapped.append(f"{self.path}:{node.lineno}: {name}()")
        self.generic_visit(node)

for py in Path("app").rglob("*.py"):
    try:
        tree = ast.parse(py.read_text())
    except SyntaxError:
        continue
    Visitor(str(py)).visit(tree)

if unwrapped:
    print(f"  ⚠ {len(unwrapped)} guapo-facing calls not wrapped in try/except:")
    for u in unwrapped[:5]:
        print(f"      {u}")
    print("  (warning only — agent 4 has the full review)")
else:
    print("  ✓ guapo-facing calls in app/ are wrapped in try/except")
PY
)
echo "$unwrapped"

# ────────────────────────────────────────────────────────────────────────────
# 8. red-team (agent 3) — skipped locally
# ────────────────────────────────────────────────────────────────────────────

step "8/9  red-team"

if [[ $FULL_RUN -eq 1 ]]; then
    warn "red-team probes need a built container — running --full mode"
    if require docker "https://docs.docker.com/install/"; then
        # Build and run the smoke flow which includes the locked-tab assertion
        if docker build -f docker/app/Dockerfile -t wize73-app:preflight . &>/tmp/preflight-build.log; then
            pass "image built"
            python3 docker/smoke_test.py --image wize73-app:preflight --name preflight-app
            if [[ $? -eq 0 ]]; then
                pass "smoke test passed (locked tab markers verified)"
            else
                fail "smoke test failed"
            fi
        else
            fail "docker build failed"
            tail -20 /tmp/preflight-build.log | sed 's/^/      /'
        fi
    fi
else
    warn "skipped (use --full to enable; needs docker + container build)"
fi

# ────────────────────────────────────────────────────────────────────────────
# 9. build-and-smoke (agent 7) — already covered above in full mode
# ────────────────────────────────────────────────────────────────────────────

step "9/9  build-and-smoke"

if [[ $FULL_RUN -eq 1 ]]; then
    pass "covered above in --full red-team step"
else
    warn "skipped (use --full to enable)"
fi

# ────────────────────────────────────────────────────────────────────────────
# Summary
# ────────────────────────────────────────────────────────────────────────────

elapsed=$(($(date +%s) - START_TIME))
echo
echo -e "${BOLD}════════════════════════════════════════════════════════════${N}"
if [[ ${#FAILURES[@]} -eq 0 ]]; then
    echo -e "  ${G}${BOLD}✓ preflight passed${N} (${elapsed}s)"
    echo
    echo "  Push with confidence. CI will run the full versions."
    exit 0
else
    echo -e "  ${R}${BOLD}✗ preflight failed${N} — ${#FAILURES[@]} issue(s) (${elapsed}s)"
    echo
    for f in "${FAILURES[@]}"; do
        echo -e "  ${R}-${N} $f"
    done
    echo
    echo "  Fix these locally before pushing — saves a CI cycle."
    echo "  Run ./scripts/explain-failure.sh for help interpreting any of these."
    exit 1
fi
