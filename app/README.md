# `app/` — your code

**This is where you work.** Everything under this directory is student-editable
without instructor review. Open a PR, get 9 agents green, merge.

## What lives here

| Path | What it holds | v1 state |
|---|---|---|
| `main.py` | FastAPI entrypoint that mounts `core/chat` and `core/observability`. | Minimal wiring. |
| `personas/` | Persona definitions (YAML or JSON files). | Empty — add your own. |
| `examples/` | Few-shot example blocks. | Empty. |
| `system_prompts/` | System prompt variants students can add. | One minimal default. |
| `templates/` | Jinja2 HTML templates for the chat UI (not the metrics tab). | The dumb v1 chat UI. |
| `static/` | CSS / JS / images for your UI. | Empty. |

## What you can change

- **Anything in this directory.** Add personas, rewrite the chat template,
  restyle the UI, add new routes, refactor `main.py`, write tests.
- **The shape of the request.** `build_request()` in `core/chat/` takes
  labelled slots — you fill the slots.

## What you cannot change

- `core/` — the measurement tab, client wrapper, timing, agents, ops dashboard.
- `docker/` — container definitions.
- `.github/` — CI agents and deploy workflow.
- `docs/wiki/` — documentation (file an issue if you spot a wiki bug).
- `.devcontainer/` — Codespaces config.
- `core/python/requirements.txt` — no new deps without an instructor issue.

## The loop

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full workflow. In short:

```
branch → edit → ./scripts/preflight.sh → commit → push → PR → iterate → merge
```

## What the dumb v1 chatbot does (and doesn't)

**Does:** takes one user message, sends it to phi-4-mini with a baseline
system prompt, streams the response back, records per-turn metrics.

**Doesn't:** remember previous turns, swap personas, load few-shot examples,
validate input, handle errors gracefully, look nice, support voice, adapt
temperature, show streaming indicators, or basically any other feature of
a real chatbot.

Each of those "doesn't" is a starter issue in the [Feature Backlog](../../../wiki/07-Feature-Backlog).
Pick one and ship it.
