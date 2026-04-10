# `core/observability/` — the `/metrics` sub-app

Locked. Mounted as a separate FastAPI sub-app so it **survives app crashes** —
if a student PR breaks the chatbot router, the metrics tab keeps working and
students can still see what broke.

## What lives here

- `app.py` — the sub-app itself, mounted at `/metrics`.
- `ring_buffer.py` — per-turn records (token flow, timing, processing). Fixed
  size, in-memory, no DB.
- `token_flow.py` — decomposes each turn's input into labelled categories
  (system / persona / few-shot / history / user) and output. Feeds the pyramid
  chart.
- `timing_summary.py` — rolls up `t0..t5` from `core/timing/` into the pre-vs-post
  processing stacked bar.
- `projection.py` — the calculator. Takes an architecture spec (slot sizes,
  planned turns) and projects per-turn token + FLOPs curves using rolling-window
  coefficients (tok/s, tokenizer ratios).
- `guapo_stats.py` — `GuapoStatsProvider` abstraction with two implementations:
  - `IndirectProvider` (current) — uses only the frozen surface: `/healthz`,
    `/v1/models`, background health-RTT sampling with rolling stddev, plus the
    most recent chat call's TTFT and decode rate.
  - `DirectProvider` (stub) — ready for the day `/v1/stats` exists on guapo.
  A config flag selects which one; everything upstream is unchanged.
- `slim_stats.py` — polls the host sidecar on the internal docker network.
- `charts.py` — server-rendered SVG for the bidirectional pairs.
- `templates/` — HTMX-driven HTML partials for the metrics tab.
- `routes.py` — `/metrics`, `/metrics/flow`, `/metrics/stats/slim`,
  `/metrics/stats/guapo`, `/metrics/projection`, `/metrics/trajectory`.

## What the metrics tab shows (v1)

1. **Input vs output tokens** — pyramid bar per turn
2. **Pre vs post processing time** — horizontal stacked bar per turn
3. **Prefill vs decode compute (FLOPs)** — side-by-side bars
4. **Twin network sparklines (slim only)** — rx/tx bytes per second
5. **Cumulative session trajectory** — mirrored stacked area (input above, output below)
6. **Input/output asymmetry scatter** — (input_tok, output_tok) per turn with `y=x` line
7. **Slim host panel** — CPU, RAM, disk aggregates from the sidecar
8. **Guapo indirect panel** — liveness, health RTT 60s avg, chat queue signal
   (rolling RTT stddev), last TTFT, last decode rate, whisper/tts loaded flags
9. **Projection calculator** — input form → projected per-turn curves

The **prefill-vs-decode energy pair is deliberately omitted** because guapo
doesn't expose a watts signal on the frozen surface. If that endpoint is added
later, the `DirectProvider` slot is ready for it.

## Why this is a separate sub-app

Because it outlives bugs. A student PR that breaks `app/main.py` doesn't take
down `/metrics` — the sub-app is mounted independently and has zero dependency
on student-editable code. When chat is broken, observability still tells you
what broke.
