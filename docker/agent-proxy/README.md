# `docker/agent-proxy/` — CI inference proxy for agent LLM calls

Runs on slim. Exposes a single authenticated route at
`https://class.wize73.com/agents-llm` (gated by a bearer token provided as
a GitHub Actions secret) and forwards requests to guapo's
`/v1/chat/completions` over Tailscale.

## Why a proxy

GH-hosted runners can't reach guapo directly (it's on Tailscale inside the
instructor's LAN). Two options:

- Bring Tailscale up inside the GH Actions job (adds moving parts, exposes
  OAuth secret)
- **Route through slim via Cloudflare Tunnel** (simpler, smaller trust
  surface, one auth gate)

This proxy is the second option. It's the only thing on the internet that
talks to guapo, and it only accepts `chat.completions` shape — no tool use,
no embeddings, no audio, no arbitrary endpoint forwarding. The frozen
surface is protected by an even smaller frozen sub-interface.

## Features

- Bearer-token auth (token is a GitHub Actions secret)
- Per-PR rate limiting (default 10 calls/min/PR, tunable)
- Global rate limit (default 30 calls/min, tunable)
- Response caching by SHA of (model, messages)
- Kill-switch env var that returns 503 to all CI traffic — flipped from the
  instructor ops dashboard
- Structured logging, forwarded to the ops dashboard event stream

## Priority

Student traffic to the live chatbot **always** has priority over CI LLM
calls. When the kill switch flips, CI starts failing agents (fail-closed),
the instructor unpauses once the live class load drops.
