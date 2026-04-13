"""FastAPI entrypoint for the class.wize73.com chatbot.

This is the dumb v1 chatbot the class starts with. Students can edit
anything in this file — add routes, change templates, wire in new
features. The locked core/ modules are consumed but never edited.

Mounts three sub-apps:

* ``/metrics`` — the locked observability dashboard (token flow, timing,
  projection calculator, host stats). Students see this; they can't
  change it.
* ``/ops`` — the locked instructor-only ops dashboard (event stream,
  kill switches). Students can't see it — Cloudflare Access gates the
  URL to the instructor's email only.
* ``/`` — the student-editable chat UI, served from ``app/templates/``.

The chat handler uses :func:`core.chat.build_request` to assemble a
:class:`core.chat.LabelledMessages` from the labelled slots, streams a
completion from guapo via :func:`core.chat.stream_completion`, and
submits the per-turn token-flow snapshot to the observability ring
buffer so the metrics tab can show what the turn cost.

v1 only populates the ``baseline`` and ``user`` slots. Students extend
by wiring in personas, examples, and history as they implement features.
"""

from __future__ import annotations

import html
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.chat import (
    ChatError,
    FilterBlocked,
    UpstreamTimeout,
    UpstreamUnavailable,
    build_request,
    count_tokens,
    stream_completion,
)
from core.observability import (
    IndirectProvider,
    MetricsState,
    RingBuffer,
    SlimStatsClient,
    TokenFlowSnapshot,
    create_metrics_app,
)
from core.ops import OpsState, create_ops_app
from core.prompts import load_baseline, load_mentor
from core.timing import instrument

# ────────────────────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────────────────────

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
APP_TEMPLATES_DIR = APP_DIR / "templates"
APP_STATIC_DIR = APP_DIR / "static"
CORE_TEMPLATES_DIR = REPO_ROOT / "core" / "templates"

# ────────────────────────────────────────────────────────────────────────────
# Shared state — created once at module load and plumbed into sub-apps
# ────────────────────────────────────────────────────────────────────────────

ring_buffer = RingBuffer()

_guapo_provider = IndirectProvider.from_env()
_slim_client = SlimStatsClient()

metrics_state = MetricsState(
    ring_buffer=ring_buffer,
    guapo_provider=_guapo_provider,
    slim_client=_slim_client,
)

ops_state = OpsState()

# Baseline system prompt is loaded from core/prompts/baseline.md (locked).
BASELINE_PROMPT = load_baseline()

# Mentor system prompt is loaded from core/prompts/mentor.md (locked).
# Used by the /guide/chat endpoint — teaches without doing.
MENTOR_PROMPT = load_mentor()

PROMPT_B_SUFFIX = """
You are comparing prompt strategies for a classroom exercise.
Answer as a more structured teaching assistant.
Be clear, step by step, and slightly more explanatory than the default.
""".strip()

# ────────────────────────────────────────────────────────────────────────────
# Templates — search app/templates/ first, then core/templates/ for base.html
# ────────────────────────────────────────────────────────────────────────────

templates = Jinja2Templates(directory=[str(APP_TEMPLATES_DIR), str(CORE_TEMPLATES_DIR)])

# ────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="class.wize73.com", docs_url=None, redoc_url=None)

if APP_STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(APP_STATIC_DIR)), name="static")

# Mount the locked sub-apps. Timing emitter is wired inside create_metrics_app.
app.mount("/metrics", create_metrics_app(metrics_state))
app.mount("/ops", create_ops_app(ops_state))


def _render_error(
    message: str,
    status_code: int = 500,
    css_class: str = "assistant-response",
) -> HTMLResponse:
    """Render a small HTMX-friendly error fragment."""
    return HTMLResponse(
        content=(f'<div class="{css_class} error">' f"{html.escape(message)}" "</div>"),
        status_code=status_code,
    )


async def _collect_output(messages: object, timer: object) -> tuple[str, int]:
    """Stream a completion and return the joined text and token count."""
    output_parts = [chunk async for chunk in stream_completion(messages, instrument=timer)]
    output_text = "".join(output_parts)
    output_tokens = count_tokens(output_text)
    return output_text, output_tokens


def _submit_flow(
    request_id: str,
    messages: object,
    output_tokens: int,
) -> None:
    """Submit token flow data to the observability ring buffer."""
    ring_buffer.submit_flow(
        request_id,
        TokenFlowSnapshot(
            system_tokens=messages.system_tokens,
            persona_tokens=messages.persona_tokens,
            examples_tokens=messages.examples_tokens,
            history_tokens=messages.history_tokens,
            user_tokens=messages.user_tokens,
            output_tokens=output_tokens,
        ),
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Render the styled landing page with exercise instructions."""
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={},
    )


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request) -> HTMLResponse:
    """Render the chatbot UI (student-editable)."""
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={},
    )


@app.get("/guide", response_class=HTMLResponse)
async def guide_page(request: Request) -> HTMLResponse:
    """Render the AI Guide with the mentor chatbot."""
    return templates.TemplateResponse(
        request=request,
        name="guide.html",
        context={},
    )


@app.get("/docs", response_class=HTMLResponse)
async def docs_page(request: Request) -> HTMLResponse:
    """Render the comprehensive course manual (one scrollable page)."""
    return templates.TemplateResponse(
        request=request,
        name="docs.html",
        context={},
    )


@app.post("/chat", response_class=HTMLResponse)
async def chat(
    request: Request,
    user_message: str = Form(...),
    compare_mode: str | None = Form(default=None),
) -> HTMLResponse:
    """Chat handler with optional A/B prompt comparison mode."""
    del request

    user_message = user_message.strip()
    if not user_message:
        return _render_error("Type something first.", status_code=400)

    is_compare_mode = compare_mode == "true"

    try:
        if not is_compare_mode:
            with instrument() as t:
                messages = build_request(
                    baseline=BASELINE_PROMPT,
                    user=user_message,
                )
                t.mark("t1")

                output_text, output_tokens = await _collect_output(messages, t)
                _submit_flow(t.request_id, messages, output_tokens)

            safe_output = html.escape(output_text)
            response_html = (
                '<div class="assistant-response">'
                "<strong>assistant:</strong><br>"
                f"<pre>{safe_output}</pre>"
                "</div>"
            )
        else:
            prompt_a = BASELINE_PROMPT
            prompt_b = f"{BASELINE_PROMPT}\n\n{PROMPT_B_SUFFIX}"

            with instrument() as t_a:
                messages_a = build_request(
                    baseline=prompt_a,
                    user=user_message,
                )
                t_a.mark("t1")

                output_text_a, output_tokens_a = await _collect_output(messages_a, t_a)
                _submit_flow(t_a.request_id, messages_a, output_tokens_a)

            with instrument() as t_b:
                messages_b = build_request(
                    baseline=prompt_b,
                    user=user_message,
                )
                t_b.mark("t1")

                output_text_b, output_tokens_b = await _collect_output(messages_b, t_b)
                _submit_flow(t_b.request_id, messages_b, output_tokens_b)

            safe_output_a = html.escape(output_text_a)
            safe_output_b = html.escape(output_text_b)

            response_html = (
                '<div class="compare-results">'
                '<div class="assistant-response compare-card">'
                "<strong>Prompt A — baseline</strong><br>"
                f"<pre>{safe_output_a}</pre>"
                "</div>"
                '<div class="assistant-response compare-card">'
                "<strong>Prompt B — teaching style</strong><br>"
                f"<pre>{safe_output_b}</pre>"
                "</div>"
                "</div>"
            )

    except UpstreamUnavailable:
        return _render_error(
            "The inference service is unavailable right now. Try again in a moment.",
            status_code=503,
        )
    except UpstreamTimeout:
        return _render_error(
            "The inference service timed out. Try a shorter prompt.",
            status_code=504,
        )
    except FilterBlocked:
        return _render_error(
            "Response was filtered for security. Please try rephrasing.",
            status_code=502,
        )
    except ChatError:
        return _render_error(
            "Something went wrong with the chat call.",
            status_code=500,
        )

    return HTMLResponse(content=response_html)


@app.post("/guide/chat", response_class=HTMLResponse)
async def mentor_chat(
    request: Request,
    user_message: str = Form(...),
) -> HTMLResponse:
    """Mentor chatbot on the AI Guide tab. Same backend, teaching prompt.

    Uses the locked mentor system prompt from core/prompts/mentor.md.
    No student overlay, no persona — the mentor is fully locked so
    students can't change it to "write my PR for me."
    """
    del request

    user_message = user_message.strip()
    if not user_message:
        return HTMLResponse(
            content='<div class="mentor-response error">Type a question first.</div>',
            status_code=400,
        )

    try:
        with instrument() as t:
            messages = build_request(
                baseline=MENTOR_PROMPT,
                user=user_message,
            )
            t.mark("t1")

            output_parts = [chunk async for chunk in stream_completion(messages, instrument=t)]
            output_text = "".join(output_parts)
            output_tokens = count_tokens(output_text)

            _submit_flow(t.request_id, messages, output_tokens)
    except UpstreamUnavailable:
        return HTMLResponse(
            content=(
                '<div class="mentor-response error">'
                "The inference service is unavailable. Try again in a moment."
                "</div>"
            ),
            status_code=503,
        )
    except UpstreamTimeout:
        return HTMLResponse(
            content=(
                '<div class="mentor-response error">'
                "The inference service timed out. Try a shorter question."
                "</div>"
            ),
            status_code=504,
        )
    except ChatError:
        return HTMLResponse(
            content=(
                '<div class="mentor-response error">' "Something went wrong. Try again." "</div>"
            ),
            status_code=500,
        )

    safe_output = html.escape(output_text)
    return HTMLResponse(
        content=(
            '<div class="mentor-response">'
            "<strong>mentor:</strong><br>"
            f"<pre>{safe_output}</pre>"
            "</div>"
        )
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe for the main app."""
    return {"status": "ok"}
