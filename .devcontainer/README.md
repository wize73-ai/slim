# `.devcontainer/` — Codespaces configuration

Locked. This directory configures the cloud development environment that
opens when you click **Code → Codespaces → Create codespace**.

## Why Codespaces

Because you have 2.5 hours to learn the workflow, not 20 minutes to debug
a local Python install. Codespaces gives every student an identical,
working dev environment in about 30 seconds of browser startup.

## What's pre-installed

- Python 3.12 with the full dependency set from `core/python/`
- Ruff, mypy, pytest, interrogate (the same tools the agents use)
- ripgrep (`rg`), ctags, `gh` CLI, jq
- VS Code extensions: Python, Ruff, GitLens, Jinja, HTMX snippets
- Pre-commit hook that runs `ruff check --fix` on save
- The `OPENAI_BASE_URL` env var pre-configured to reach guapo via the
  agent proxy (students don't see the raw URL)
- `scripts/preflight.sh` and `scripts/explain-failure.sh` on PATH

## What's not installed

- No production secrets. The Codespace can run the app locally against
  the dev proxy, but it cannot deploy.
- No Tailscale client. Students reach guapo indirectly through the
  proxy, not over Tailscale.
- No Docker-in-Docker. Students don't build production images in their
  Codespace — that's the deploy workflow's job.

## Locked

Students cannot edit these files. The devcontainer has to stay consistent
across students for the class to work — if one student "customizes" their
environment mid-class, we lose reproducibility.
