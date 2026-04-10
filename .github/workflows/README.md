# `.github/workflows/` — CI/CD workflows

Locked. **Ten workflow files** when complete:

## Pre-merge agents (run on every PR, all 9 must pass)

| # | File | Purpose |
|---|---|---|
| 1 | `pr-01-secrets-scan.yml` | gitleaks + semgrep + narrow LLM obfuscation-property check |
| 2 | `pr-02-code-quality.yml` | ruff strict + mypy + pytest + interrogate + LLM pythonic review |
| 3 | `pr-03-red-team.yml` | 12 pre-written adversarial probes + deterministic checks + LLM judge |
| 4 | `pr-04-blue-team.yml` | Defensive static checks + LLM residual review |
| 5 | `pr-05-classroom-safety.yml` | Regex word list + LLM secondary on prompt/persona files |
| 6 | `pr-06-version-discipline.yml` | Pinned deps, locked-core guard, conventional commits, up-to-date |
| 7 | `pr-07-build-and-smoke.yml` | Docker buildx + smoke test hitting `/healthz` and `/metrics/*` |
| 8 | `pr-08-slop-and-scope.yml` | Python AST analysis for dead code / duplication / scope creep |
| 9 | `pr-09-malicious-code-review.yml` | Dual-judge malice scan with static + LLM layers |

## Deploy (runs on merge to main)

| File | Purpose |
|---|---|
| `deploy-on-main.yml` | Build image, push to GHCR, SSH to slim via Tailscale, run `deploy.sh` |

## Security model

**Workflows that execute student code have NO secrets.** Specifically,
`pr-07-build-and-smoke.yml` and `pr-03-red-team.yml` run the PR's container
with an empty secret set. Only agents that read the diff (as text) have
access to the `AGENT_PROXY_TOKEN` secret for LLM calls.

**Only `deploy-on-main.yml` runs with deploy secrets**, and it never
executes student code at workflow time — it pulls a pre-built image from
GHCR and hands off to a fixed `deploy.sh` on slim.

## LLM calls route through slim

All agent LLM calls go to `https://class.wize73.com/agents-llm` (the agent
inference proxy on slim). No direct calls to guapo, no external APIs. The
proxy enforces rate limits and can be killed from the ops dashboard if
guapo starts starving live student traffic.
