# class.wize73.com — AI Chatbot Teaching Project

A classroom exercise in modern chatbot design. Students inherit a
deliberately bad single-turn chatbot and a fully working measurement rig,
then improve the chatbot while watching the metrics move.

The teaching spine is **token flow and processing effort** — every design
decision has a measurable cost in tokens, time, and compute, and every
bidirectional pair (input vs output, prefill vs decode, pre vs post
processing, network in vs out) reveals a different lesson.

## Repository layout

| Path | What it is | Who edits |
|---|---|---|
| `app/` | **Your code.** Personas, system prompts, few-shot examples, chat templates, static assets. | Students |
| `core/` | **Locked.** Measurement tab, OpenAI client wrapper, labelled request slots, security preamble, agent runners, instructor ops dashboard. CODEOWNERS-protected so the numbers stay trustworthy across PRs. | Instructor only |
| `docker/` | Container definitions for the app, stats sidecar, agent inference proxy, egress firewall. | Instructor only |
| `docs/wiki/` | Source of truth for the GitHub Wiki. | Instructor only |
| `scripts/` | Helper scripts (`preflight.sh`, `explain-failure.sh`). | Shared |
| `.devcontainer/` | Codespaces configuration — click *Code → Codespaces → Create* and you're coding in under 30 seconds. | Instructor only |
| `.github/` | CI agents (9 of them), deploy workflow, issue/PR templates, CODEOWNERS. | Instructor only |

## Quick start for students

1. Click **Code → Codespaces → Create codespace on main**
2. Wait ~30 seconds for the environment to boot
3. Pick an issue from the [Feature Backlog](../../wiki/07-Feature-Backlog)
4. Create a branch, open a PR, read what the agents tell you
5. Push until the agents are green, then merge
6. Your change is live at [class.wize73.com](https://class.wize73.com) within ~90 seconds

First time through: read [Your First PR](../../wiki/04-Your-First-PR).

## The architecture at a glance

```
                  ┌──────────────────────────────────────┐
    12 students   │       Cloudflare edge                │
    (browser) ──▶ │  TLS · Access SSO · WAF              │
                  └──────────────┬───────────────────────┘
                                 │ Cloudflare Tunnel (outbound)
                                 ▼
                  ┌──────────────────────────────────────┐
                  │  slim (deploy box, on LAN+Tailscale) │
                  │    ├─ app container  (FastAPI + HTMX)│
                  │    ├─ stats sidecar  (psutil host)   │
                  │    ├─ agent proxy    (CI → guapo)    │
                  │    └─ cloudflared    (tunnel agent)  │
                  └──────────────┬───────────────────────┘
                                 │ Tailscale (private)
                                 ▼
                  ┌──────────────────────────────────────┐
                  │  guapo (inference, RTX 3070)         │
                  │    ├─ phi-4-mini     (chat via vLLM) │
                  │    ├─ whisper        (STT)           │
                  │    └─ XTTS-v2        (TTS)           │
                  │  Frozen surface — contract only,     │
                  │  see speech-service INTERFACE.md.    │
                  └──────────────────────────────────────┘
```

Inference on guapo stays on guapo. Observability on slim stays on slim.
The deploy box never holds secrets the agents don't need, and the model
host never touches the public internet.

## Documentation

- [Architecture](../../wiki/01-Architecture)
- [Contribution Workflow](../../wiki/02-Contribution-Workflow)
- [Bidirectional Framing](../../wiki/03-Bidirectional-Framing) — the central idea
- [Your First PR](../../wiki/04-Your-First-PR)
- [Agents Reference](../../wiki/05-Agents-Reference)
- [Troubleshooting](../../wiki/06-Troubleshooting)
- [Feature Backlog](../../wiki/07-Feature-Backlog)

## Ground rules (short version)

- You can edit anything under `app/`. Everything else is CODEOWNERS-locked.
- You cannot add new Python dependencies. File an issue instead.
- Every PR runs 9 pre-merge agents. All must pass. They explain themselves.
- Conventional commits required (`feat:`, `fix:`, `docs:`, `refactor:`, ...).
- Tell us what AI assistant you used in the PR template. It's not a gotcha.
- `./scripts/preflight.sh` runs the agents locally in ~30s — use it.

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full rules.
