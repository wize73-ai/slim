# Architecture

Three hosts, one frozen API surface, defense in depth.

## Three-host topology

```
                    Cloudflare edge
              (TLS · Access SSO · WAF)
                          │
              Cloudflare Tunnel (outbound)
                          │
                  ┌───────▼─────────┐
                  │  slim           │  ← deploy box (LAN+Tailscale)
                  │   ├ app         │       FastAPI + HTMX, what you build
                  │   ├ stats       │       psutil sidecar (host metrics)
                  │   ├ agent-proxy │       CI → guapo only path
                  │   └ cloudflared │       inbound tunnel only
                  └───────┬─────────┘
                          │ Tailscale (private)
                          ▼
                  ┌─────────────────┐
                  │  guapo          │  ← inference (RTX 3070)
                  │   ├ phi-4-mini  │       chat (vLLM)
                  │   ├ whisper     │       speech-to-text
                  │   └ XTTS-v2     │       text-to-speech
                  │  Frozen surface │
                  └─────────────────┘
```

- **Students** reach `class.wize73.com` over HTTPS via Cloudflare. No
  Tailscale client needed. Cloudflare Access can gate by email if the
  instructor has set it up.
- **slim** runs the chatbot, the host-stats sidecar, the agent
  inference proxy (CI's only path to guapo), and `cloudflared` (the
  outbound tunnel agent). Hardened: read-only rootfs, dropped caps,
  non-root user, egress firewall.
- **guapo** runs the inference models. Stays inside the LAN +
  Tailscale, never touches the internet. Its API surface is **frozen**
  — see `INTERFACE.md` in the speech-service repo for the contract.
- **GitHub Actions** runners build images, push to GHCR, then SSH to
  slim via Tailscale (using Tailscale SSH — no SSH key in repo
  secrets) to run the deploy script.

## The locked core

`core/` is CODEOWNERS-protected. Students consume its APIs but cannot
edit any module under it. The locked surface guarantees that:

1. **Measurement integrity** — the per-turn token decomposition, the
   timing instrumentation, the projection coefficients, all stay
   consistent across PRs. Two PRs that report the same numbers are
   actually doing the same amount of work.
2. **Security boundary** — the security preamble (that tells the
   model never to leak guapo's URL/IPs/model names) and the output
   filter (that catches leaks anyway) cannot be bypassed by student
   code.
3. **Dependency lock** — `requirements.txt` is in
   `core/python/` and CODEOWNERS-protected. Students cannot add Python
   packages without an instructor issue. Closes the supply-chain
   attack vector entirely.

What's inside `core/`:

| Subpackage | What it does |
|---|---|
| `core/chat/` | OpenAI client wrapper, `build_request()` with labelled slots, security preamble, output filter |
| `core/observability/` | The `/metrics` sub-app, ring buffer, projection calculator, dashboards |
| `core/ops/` | The `/ops` instructor-only dashboard (event stream, kill switches) |
| `core/timing/` | `t0..t5` per-request instrumentation |
| `core/agents/` | Prompts + rules + Python helpers for the 9 PR agents |
| `core/prompts/` | Baseline locked system prompt |

## The 9 PR agents

Every pull request runs these 9 agents in parallel (~150 seconds total
wall time) and all must pass before merge:

| # | Agent | What it checks |
|---|---|---|
| 1 | `secrets-scan` | Hardcoded secrets, leaked URLs, obfuscation property |
| 2 | `code-quality` | ruff strict + mypy strict + pytest + interrogate |
| 3 | `red-team` | 12 adversarial probes against your built container |
| 4 | `blue-team` | Defensive code review (missing error handling, etc.) |
| 5 | `classroom-safety` | Content review of new persona/prompt files |
| 6 | `version-discipline` | Pinned deps, locked paths, conventional commits |
| 7 | `build-and-smoke` | Builds image, runs smoke test (locks metrics tab) |
| 8 | `slop-and-scope` | AST dead-code + scope-vs-issue check |
| 9 | `malicious-code-review` | Insider-threat detection, dual judge |

See [Agents Reference](05-Agents-Reference) for one page per agent.

## Defense in depth

The threat model assumes that one or more students will be clever and
try to do something they shouldn't. The defenses are layered so no
single failure compromises the system:

1. **Pre-merge**: 9 agents scan every PR. Static rules catch ~80%.
   LLM judges catch the fuzzy ~15%. Instructor approval handles the
   final 5%.
2. **Build-time**: `core/` and `docker/` and `.github/` are
   CODEOWNERS-protected. The dependency manifest is locked.
3. **Runtime**: the app container runs read-only, drops all caps,
   non-root, no host mounts, with strict resource caps.
4. **Network**: an nftables egress allow-list on the app container's
   namespace permits only guapo:8000 + cloudflared + localhost DNS.
   Everything else is dropped and logged. Cryptominers, reverse
   shells, and network scanners cannot phone home even if they make
   it past every other layer.
5. **Behavioral**: even if the model is somehow tricked into trying
   to leak guapo's URL, the output filter regex-redacts it from the
   SSE stream before it reaches the browser.
6. **Audit**: the instructor ops dashboard (`/ops`) shows live event
   stream of agent results, deploys, and firewall drops. The
   instructor monitors during class.

## Bidirectional metrics framing

The central mental model: every metric in the system has an in/out or
pre/post axis, and the *asymmetry* between the two halves is where
the lessons live. See [Bidirectional Framing](03-Bidirectional-Framing)
for the full explanation. Short version: input tokens vs output tokens
is the simplest pair, and "what's your asymmetry ratio?" is one of the
best questions you can ask about a chat turn.
