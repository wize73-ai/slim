#!/usr/bin/env bash
# Codespaces post-start hook — runs every time the container starts
# (including resume from sleep). Keep it cheap.

set -euo pipefail

cd /workspaces/slim 2>/dev/null || cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# Ensure the ctags index is current. Cheap if nothing changed.
if command -v ctags >/dev/null; then
    ctags -R \
        --exclude=.git \
        --exclude=.gitnexus \
        --exclude=__pycache__ \
        --exclude=.venv \
        --exclude=node_modules \
        --languages=python,html \
        -f tags \
        . 2>/dev/null || true
fi
