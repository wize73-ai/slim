#!/usr/bin/env python3
"""Mock guapo — tiny OpenAI-compatible server for local dev.

Real guapo lives on the instructor's LAN/Tailscale and is not reachable
from a Codespace. This mock implements just enough of the frozen surface
to let students iterate on the chatbot UI, the metrics tab, and the
projection calculator without needing real inference.

Run with::

    python .devcontainer/mock-guapo.py &

Then point the chatbot at it::

    OPENAI_BASE_URL=http://127.0.0.1:9999/v1 uvicorn app.main:app --port 8080

Endpoints implemented:

* ``GET  /healthz`` — liveness, returns {"status":"ok"}
* ``GET  /v1/models`` — returns the three frozen IDs (phi-4-mini,
  whisper, xtts) so the chatbot's model catalog populates.
* ``POST /v1/chat/completions`` — returns canned text shaped like a
  real OpenAI response (with usage tokens) so the metrics tab gets
  realistic-looking data. The text is deterministic per input so the
  cache layer in the agent proxy works.

What it does NOT implement:

* Actual inference. The mock is for UI iteration only. Real chat
  responses come from guapo on the deployed app.
* Audio endpoints. The mock can be extended later if students want to
  iterate on voice features locally.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="mock-guapo", docs_url=None, redoc_url=None)


class _ChatMessage(BaseModel):
    role: str
    content: str


class _ChatRequest(BaseModel):
    model: str
    messages: list[_ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 512
    stream: bool = False


# A bank of canned responses. Selection is deterministic by input hash
# so the agent-proxy cache (which keys on input) works correctly with
# the mock.
_RESPONSES = [
    "I'm a mock response from a local development server. Real chat "
    "happens when you push and the app deploys.",
    "Mock guapo here. The metrics tab is showing real timing and token "
    "data — that's the point of running me. Iterate on the UI; the "
    "chatbot will get its real voice when it ships.",
    "This is canned text. The point of running this mock is so you can "
    "see the metrics tab populate and feel the request/response loop.",
    "Hello from the dev mock. To see the actual model respond, push "
    "your branch and watch the deploy at class.wize73.com.",
    "Mock response. Token-flow looks real because it is — the mock "
    "returns enough text for tiktoken to count.",
]


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    """Liveness — returns the same shape as guapo's real /healthz."""
    return {"status": "ok", "whisper_loaded": False, "tts_loaded": False}


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    """Return the three frozen model IDs so the chatbot catalog populates."""
    return {
        "object": "list",
        "data": [
            {
                "id": "/models/phi-4-mini",
                "object": "model",
                "owned_by": "vllm",
                "created": int(time.time()),
            },
            {
                "id": "large-v3-turbo",
                "object": "model",
                "owned_by": "speech-service",
                "capabilities": ["audio.transcriptions"],
            },
            {
                "id": "tts_models/multilingual/multi-dataset/xtts_v2",
                "object": "model",
                "owned_by": "speech-service",
                "capabilities": ["audio.speech"],
            },
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: _ChatRequest) -> dict[str, Any]:
    """Return a canned response shaped like the real OpenAI API."""
    # Pick a deterministic response based on the input hash so the
    # agent-proxy cache layer behaves correctly.
    body = "\n".join(m.content for m in req.messages)
    digest = int(hashlib.sha256(body.encode()).hexdigest(), 16)
    response_text = _RESPONSES[digest % len(_RESPONSES)]

    # Approximate tokens (4 chars per token is a reasonable rule of thumb).
    prompt_tokens = max(1, len(body) // 4)
    completion_tokens = max(1, len(response_text) // 4)

    return {
        "id": f"mock-{digest:x}"[:24],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=9999, log_level="info")
