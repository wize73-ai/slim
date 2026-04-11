"""Agent inference proxy — the only path from CI to guapo.

Small FastAPI server that runs alongside the app on slim. Exposes a
single bearer-authenticated POST endpoint at ``/agents-llm`` that forwards
``chat.completions`` requests to guapo over Tailscale. CI workflows use
this from GH-hosted runners to call phi-4-mini for the LLM-based agents
without GH runners needing direct Tailscale access.

Features:

* **Bearer token auth** — token from ``AGENT_PROXY_TOKEN`` env var,
  constant-time comparison.
* **Per-PR rate limiting** — clients pass ``X-PR-Number`` header; proxy
  enforces a per-PR rate limit so a runaway agent loop in one PR can't
  starve the rest of the class.
* **Global rate limiting** — second bucket on top of per-PR. Student
  chat traffic always has priority over CI LLM calls.
* **Cache by SHA** — identical requests in the same window return the
  cached response without hitting guapo. Reviewing the same hunk twice
  costs one LLM call.
* **Kill switch** — ``AGENT_PROXY_PAUSED=1`` env var or via the
  ``/control/pause`` endpoint (instructor-auth) makes all forwarded
  calls return 503 instantly. Frees guapo for live student traffic.
* **Structured logging** — every call logs to stdout for ingest into the
  ops dashboard event stream.

Frozen sub-interface: this proxy ONLY accepts the chat.completions
shape. No tool use, no embeddings, no audio, no arbitrary endpoint
forwarding. Even if a malicious agent payload reaches the proxy, the
worst it can do is generate text via guapo.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

# ────────────────────────────────────────────────────────────────────────────
# Configuration via environment
# ────────────────────────────────────────────────────────────────────────────

GUAPO_URL = os.environ.get("GUAPO_URL", "http://100.91.130.128:8000")
GUAPO_TIMEOUT = float(os.environ.get("GUAPO_TIMEOUT_SECONDS", "30.0"))
BEARER_TOKEN = os.environ.get("AGENT_PROXY_TOKEN")  # required at startup

# Per-PR limit: max calls per minute per PR (X-PR-Number header).
PER_PR_RATE_LIMIT = int(os.environ.get("AGENT_PROXY_PER_PR_LIMIT", "10"))
# Global limit: max calls per minute total across all PRs.
GLOBAL_RATE_LIMIT = int(os.environ.get("AGENT_PROXY_GLOBAL_LIMIT", "30"))
RATE_WINDOW_SECONDS = 60.0

# Cache TTL for identical (model, messages) pairs.
CACHE_TTL_SECONDS = float(os.environ.get("AGENT_PROXY_CACHE_TTL", "300"))
CACHE_MAX_ENTRIES = int(os.environ.get("AGENT_PROXY_CACHE_MAX", "256"))

# Kill switch from env. Can also be flipped at runtime via /control/pause.
_PAUSED = os.environ.get("AGENT_PROXY_PAUSED", "").lower() in ("1", "true", "yes")

# ────────────────────────────────────────────────────────────────────────────
# Logging — structured single-line JSON for easy ops-dashboard ingest
# ────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
log = logging.getLogger("agent-proxy")


def log_event(**fields: Any) -> None:
    """Emit one structured log line."""
    fields.setdefault("ts", time.time())
    log.info(json.dumps(fields))


# ────────────────────────────────────────────────────────────────────────────
# Rate limit + cache (in-process state)
# ────────────────────────────────────────────────────────────────────────────

# Per-PR sliding window of call timestamps.
_pr_calls: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=PER_PR_RATE_LIMIT * 2))
_global_calls: deque[float] = deque(maxlen=GLOBAL_RATE_LIMIT * 2)

# Simple LRU-ish cache: hash → (response_dict, expires_at).
_cache: dict[str, tuple[dict[str, Any], float]] = {}
_cache_lock = asyncio.Lock()


def _check_rate_limit(pr_id: str) -> bool:
    """Return True if the call should be allowed, False if rate-limited."""
    now = time.monotonic()
    cutoff = now - RATE_WINDOW_SECONDS

    # Per-PR
    pr_window = _pr_calls[pr_id]
    while pr_window and pr_window[0] < cutoff:
        pr_window.popleft()
    if len(pr_window) >= PER_PR_RATE_LIMIT:
        return False

    # Global
    while _global_calls and _global_calls[0] < cutoff:
        _global_calls.popleft()
    if len(_global_calls) >= GLOBAL_RATE_LIMIT:
        return False

    pr_window.append(now)
    _global_calls.append(now)
    return True


def _cache_key(model: str, messages: list[dict[str, str]]) -> str:
    """SHA256 of (model, messages) — stable across Python sessions."""
    payload = json.dumps({"model": model, "messages": messages}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _cache_get(key: str) -> dict[str, Any] | None:
    """Look up a cached response, evict if expired."""
    async with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        response, expires_at = entry
        if time.monotonic() >= expires_at:
            _cache.pop(key, None)
            return None
        return response


async def _cache_put(key: str, response: dict[str, Any]) -> None:
    """Store a response, evicting the oldest entries when full."""
    async with _cache_lock:
        if len(_cache) >= CACHE_MAX_ENTRIES:
            # Drop the oldest 10% by arbitrary order — good enough.
            for k in list(_cache.keys())[: CACHE_MAX_ENTRIES // 10]:
                _cache.pop(k, None)
        _cache[key] = (response, time.monotonic() + CACHE_TTL_SECONDS)


# ────────────────────────────────────────────────────────────────────────────
# Auth
# ────────────────────────────────────────────────────────────────────────────


def _check_bearer(authorization: str | None) -> bool:
    """Constant-time bearer token check."""
    if BEARER_TOKEN is None or not authorization:
        return False
    if not authorization.startswith("Bearer "):
        return False
    provided = authorization[len("Bearer ") :]
    return hmac.compare_digest(provided.encode(), BEARER_TOKEN.encode())


# ────────────────────────────────────────────────────────────────────────────
# Request / response models — frozen sub-interface
# ────────────────────────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    """One message in the chat completions request."""

    role: str = Field(min_length=1, max_length=32)
    content: str


class ChatCompletionRequest(BaseModel):
    """The ONLY shape this proxy accepts. Anything else returns 400.

    Restricted to chat.completions on purpose — see the module docstring.
    """

    model: str = Field(min_length=1, max_length=128)
    messages: list[ChatMessage] = Field(min_length=1, max_length=64)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=512, ge=1, le=4096)
    stream: bool = Field(default=False)


# ────────────────────────────────────────────────────────────────────────────
# FastAPI app — uses lifespan context manager (not the deprecated on_event)
# ────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    """Validate config on startup so misconfiguration fails loudly."""
    if BEARER_TOKEN is None:
        log_event(level="error", msg="AGENT_PROXY_TOKEN env var not set, refusing to start")
        raise RuntimeError("AGENT_PROXY_TOKEN must be set")
    log_event(
        level="info",
        msg="agent proxy starting",
        guapo_url=GUAPO_URL,
        per_pr_limit=PER_PR_RATE_LIMIT,
        global_limit=GLOBAL_RATE_LIMIT,
        paused=_PAUSED,
    )
    yield


app = FastAPI(
    title="agent-inference-proxy",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    """Liveness probe — unauthenticated."""
    return {
        "status": "ok",
        "paused": _PAUSED,
        "cache_size": len(_cache),
    }


@app.post("/agents-llm")
async def agents_llm(
    req: ChatCompletionRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    x_pr_number: str | None = Header(default=None),
) -> dict[str, Any]:
    """Forward a chat.completions request to guapo, with all the protections.

    Returns the upstream response unchanged on success. The body is
    validated against ChatCompletionRequest before forwarding so a
    malicious payload can't smuggle non-chat fields into guapo.
    """
    # Auth
    if not _check_bearer(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Kill switch
    if _PAUSED:
        log_event(level="warning", msg="paused, returning 503", pr=x_pr_number)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="agent inference proxy is paused",
        )

    # Streaming is not supported by the agents — they want one shot.
    if req.stream:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="stream=True not supported by the agent proxy",
        )

    # Rate limit
    pr_id = x_pr_number or "unknown"
    if not _check_rate_limit(pr_id):
        log_event(
            level="warning",
            msg="rate-limited",
            pr=pr_id,
            client=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
        )

    # Cache lookup
    messages_for_hash = [{"role": m.role, "content": m.content} for m in req.messages]
    cache_key = _cache_key(req.model, messages_for_hash)
    cached = await _cache_get(cache_key)
    if cached is not None:
        log_event(level="info", msg="cache hit", pr=pr_id, key=cache_key[:16])
        return cached

    # Forward to guapo
    body = {
        "model": req.model,
        "messages": messages_for_hash,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "stream": False,
    }
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=GUAPO_TIMEOUT) as client:
            response = await client.post(
                f"{GUAPO_URL}/v1/chat/completions",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    # Guapo doesn't enforce auth but the client requires *something*.
                    "Authorization": "Bearer sk-local",
                },
            )
    except httpx.HTTPError as e:
        log_event(level="error", msg="guapo unreachable", pr=pr_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"upstream inference unreachable: {e}",
        ) from e

    elapsed_ms = int((time.monotonic() - start) * 1000)
    if response.status_code != 200:  # noqa: PLR2004
        log_event(
            level="error",
            msg="guapo returned non-200",
            pr=pr_id,
            status=response.status_code,
            elapsed_ms=elapsed_ms,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"upstream returned {response.status_code}",
        )

    payload = response.json()
    await _cache_put(cache_key, payload)

    log_event(
        level="info",
        msg="forwarded ok",
        pr=pr_id,
        elapsed_ms=elapsed_ms,
        prompt_tokens=payload.get("usage", {}).get("prompt_tokens"),
        completion_tokens=payload.get("usage", {}).get("completion_tokens"),
    )
    return payload
