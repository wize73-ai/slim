# `docker/app/` — main chatbot app container

Base: `python:3.12-slim` (linux/amd64, matches slim's architecture).

Built and pushed to GHCR on every merge to `main` by
`.github/workflows/deploy-on-main.yml`. Deployed to slim via a blue/green
swap in `deploy.sh`.

See `../README.md` for hardening and network policy.
