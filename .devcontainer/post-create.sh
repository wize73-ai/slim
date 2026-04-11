#!/usr/bin/env bash
# Codespaces post-create hook — runs once when the dev container is built.
#
# Installs Python dependencies from the locked manifests, sets up the
# git pre-commit hook (ruff --fix + ruff format on staged Python files),
# and prints a quick orientation banner.

set -euo pipefail

echo "════════════════════════════════════════════════════════════════"
echo "  wize73 class chatbot — dev environment setup"
echo "════════════════════════════════════════════════════════════════"

cd /workspaces/slim 2>/dev/null || cd "$(git rev-parse --show-toplevel)"

echo
echo "==> installing pinned production dependencies"
pip install --user --no-cache-dir -r requirements.txt

echo
echo "==> installing pinned dev dependencies (ruff, mypy, pytest, ...)"
pip install --user --no-cache-dir -r requirements-dev.txt

echo
echo "==> installing git pre-commit hook (ruff format + ruff check --fix)"
mkdir -p .git/hooks
cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
# Auto-fix lint/format on staged Python files before every commit.
# Failures here are fixable — re-stage and commit again.
set -e
files=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.py$' || true)
if [[ -z "$files" ]]; then
    exit 0
fi
echo "==> ruff format on staged Python files"
ruff format $files
echo "==> ruff check --fix on staged Python files"
ruff check --fix $files
git add $files
HOOK
chmod +x .git/hooks/pre-commit

echo
echo "==> generating ctags index for fast symbol navigation"
ctags -R \
    --exclude=.git \
    --exclude=.gitnexus \
    --exclude=__pycache__ \
    --exclude=.venv \
    --exclude=node_modules \
    --languages=python,html \
    -f tags \
    . 2>/dev/null || true

echo
echo "════════════════════════════════════════════════════════════════"
echo "  ✓ dev environment ready"
echo "════════════════════════════════════════════════════════════════"
echo
echo "  To run the app locally:"
echo "    1. start the mock guapo:    python .devcontainer/mock-guapo.py &"
echo "    2. start the app:           uvicorn app.main:app --reload --port 8080"
echo "    3. open the forwarded port: VS Code will pop a notification"
echo
echo "  To run tests:"
echo "    pytest"
echo
echo "  To run all 9 PR agents locally before pushing (after task #14):"
echo "    ./scripts/preflight.sh"
echo
echo "  To navigate symbols:"
echo "    rg <symbol>            (ripgrep — fast text search)"
echo "    Ctrl+T in VS Code      (uses the ctags index)"
echo "    Ctrl+Click on a name   (Pylance jump-to-definition)"
echo
