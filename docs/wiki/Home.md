# class.wize73.com — AI Chatbot Teaching Project

A classroom exercise where students build a chatbot frontend while
learning what every design decision actually costs in tokens, time, and
compute. You inherit a deliberately bad single-turn chatbot and a fully
working measurement rig, then improve the chatbot while watching the
metrics move.

## The 90-second pitch

- **Real chat backend**: a self-hosted vLLM running phi-4-mini, plus
  whisper for speech-to-text and XTTS for text-to-speech. All free,
  all local, all on the same `OPENAI_BASE_URL`.
- **Real engineering loop**: branch → PR → 9 automated agents review
  → merge → live deploy at `class.wize73.com` in ~90 seconds.
- **Real measurement**: every chat turn decomposes into the labelled
  slots that fed it, with bidirectional charts showing input vs output
  tokens, prefill vs decode time, slim's network rx vs tx, etc. The
  numbers tell you what each design decision cost.

The point isn't to ship a chatbot. The point is to **feel** what
adding a 200-token system prompt does to your context budget across a
20-turn session, and to **measure** it.

## Where to start

| If you... | Read this |
|---|---|
| Just got added to the repo | [04 — Your First PR](04-Your-First-PR) |
| Don't know what the agents are | [05 — Agents Reference](05-Agents-Reference) |
| Want to understand the big picture | [01 — Architecture](01-Architecture) |
| Want to understand the metrics tab | [03 — Bidirectional Framing](03-Bidirectional-Framing) |
| Need a feature to work on | [07 — Feature Backlog](07-Feature-Backlog) |
| Got stuck or something broke | [06 — Troubleshooting](06-Troubleshooting) |

## The repo at a glance

- **`app/`** — *your code*. Personas, system prompts, few-shot examples,
  templates, static assets. Edit freely.
- **`core/`** — locked. The measurement tab, the OpenAI client wrapper,
  the security preamble, the agent runners. CODEOWNERS-protected so
  the numbers stay trustworthy across PRs.
- **`docker/`** — container definitions and the deploy scripts that
  live on the deploy box.
- **`scripts/`** — `preflight.sh` (run all 9 agents locally before
  pushing), `explain-failure.sh` (decode any agent failure).
- **`docs/wiki/`** — the source of these wiki pages.
- **`.devcontainer/`** — Codespaces config; click *Code → Codespaces →
  Create* and you have a working dev environment in 30 seconds.

## Three commands to remember

```bash
# 1. Run all 9 PR agents locally before you push (saves a CI cycle)
./scripts/preflight.sh

# 2. Get a plain-language explanation of any failing check
./scripts/explain-failure.sh

# 3. Symbol search across the codebase
rg <name>
```

## The class arc — 2.5 hours

- **0:00–0:20** — orientation, repo tour, demo chat, demo metrics
- **0:20–0:35** — everyone opens a trivial first PR, watches the
  agents run, calibrates to the feedback
- **0:35–1:50** — feature work from the [Feature Backlog](07-Feature-Backlog)
- **1:50–2:15** — red-team round; try to break each other's PRs
- **2:15–2:30** — wrap up; look at the cumulative session chart
  together, discuss which features cost more than they were worth

The metrics tab is the spine of the whole class. Keep it open in a
second browser tab. When you merge a change, watch what moves.
