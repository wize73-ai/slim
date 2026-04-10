# `app/templates/` — Jinja2 HTML templates for the chat UI

**Student-editable.** This is the UI students can redesign.

**Not editable here:** the metrics tab (`/metrics`) and ops dashboard (`/ops`)
templates live in `core/observability/templates/` and `core/ops/templates/`
respectively. Those are locked because the measurement surface has to stay
consistent across PRs.

## v1 state

- `base.html` — base layout with top nav. The nav always includes a **Metrics**
  link to `/metrics` (this part of `base.html` is rendered from a locked core
  template so students can't accidentally remove the link).
- `chat.html` — the dumb v1 chat UI. One input box, one output area, one
  submit button. Painfully bare.

## What to add

The Feature Backlog is full of UI improvements that also teach something:

- Streaming token indicator
- System prompt editor panel
- Persona picker
- Temperature slider
- Token count chip on each assistant message
- Compare-two-prompts split view
- Voice input (the STT endpoint is on guapo's frozen surface)
- Voice output (same for TTS)

## HTMX

The v1 chat UI uses HTMX for the SSE chat stream — no JS build step, no
framework to learn. You can keep using HTMX or add light vanilla JS. Don't
reach for a SPA framework; the point is to keep the dev loop fast.
