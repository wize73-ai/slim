"""Client for the agent inference proxy on slim.

The proxy is a small container running alongside the app on slim that
exposes a single bearer-authenticated endpoint at
``https://class.wize73.com/agents-llm``. It forwards `chat.completions`
requests to guapo over Tailscale, rate-limits per-PR, caches by SHA of
inputs, and can be killed instantly from the instructor ops dashboard
when guapo starts starving live student traffic.

GH-hosted runners can't reach guapo directly (it's on Tailscale inside
the instructor's LAN), so all PR-agent LLM calls go through this proxy.
The proxy is the *only* path from the internet to guapo, and it only
accepts the chat.completions shape — no tool use, no embeddings, no
arbitrary endpoint forwarding. The frozen guapo surface is protected by
an even smaller frozen sub-interface here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

# Read once at module load. Agents are typically invoked from short-lived
# CI jobs so re-reading per call is wasteful, but the values can still be
# overridden per call via the function parameters below.
_DEFAULT_PROXY_URL: Final[str] = os.environ.get(
    "AGENT_PROXY_URL", "https://class.wize73.com/agents-llm"
)
_DEFAULT_PROXY_TOKEN_ENV: Final[str] = "AGENT_PROXY_TOKEN"
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
_DEFAULT_MODEL: Final[str] = "/models/phi-4-mini"


class AgentProxyError(Exception):
    """Base for failures from the agent inference proxy.

    Catch this in runners to fail-closed: if the proxy is unavailable,
    rate-limited, or returning unexpected shapes, the agent should report
    FAIL with an explanation rather than silently passing.
    """


class AgentProxyUnavailable(AgentProxyError):
    """The proxy is unreachable, returning 5xx, or the kill switch is on."""


class AgentProxyRateLimited(AgentProxyError):
    """The proxy returned 429 — too many calls in this window."""


class AgentProxyAuthFailed(AgentProxyError):
    """The proxy returned 401/403 — bearer token missing or wrong."""


@dataclass(frozen=True, slots=True)
class ProxyResponse:
    """The shape returned by :func:`call_proxy`.

    The ``content`` is the assistant's free-text response. The ``usage``
    fields are for accounting and rate-limit headroom; they may be
    ``None`` if the proxy didn't surface them.
    """

    content: str
    prompt_tokens: int | None
    completion_tokens: int | None


async def call_proxy(
    messages: list[dict[str, str]],
    *,
    proxy_url: str | None = None,
    bearer_token: str | None = None,
    model: str = _DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 512,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> ProxyResponse:
    """Make a single chat completion call through the agent inference proxy.

    Args:
        messages: List of ``{"role": ..., "content": ...}`` dicts in the
            OpenAI chat completions format.
        proxy_url: Override the default proxy URL. Defaults to the
            ``AGENT_PROXY_URL`` env var or
            ``https://class.wize73.com/agents-llm``.
        bearer_token: Override the bearer token. Defaults to the
            ``AGENT_PROXY_TOKEN`` env var.
        model: Override the default model id. Defaults to
            ``/models/phi-4-mini``.
        temperature: Sampling temperature. Defaults to 0.0 — agents want
            deterministic output for fail-closed parsing.
        max_tokens: Max output tokens. Defaults to 512 — agents make
            narrow yes/no judgements that don't need long completions.
        timeout_seconds: Hard timeout for the call.

    Returns:
        A :class:`ProxyResponse` with the model's response text plus
        usage info.

    Raises:
        AgentProxyUnavailable: Network failure, 5xx, or kill switch.
        AgentProxyRateLimited: Proxy returned 429.
        AgentProxyAuthFailed: Proxy returned 401 or 403.
    """
    # Lazy import so this module is testable without httpx installed.
    import httpx  # noqa: PLC0415

    url = proxy_url or _DEFAULT_PROXY_URL
    token = bearer_token or os.environ.get(_DEFAULT_PROXY_TOKEN_ENV)
    if not token:
        raise AgentProxyAuthFailed(
            f"{_DEFAULT_PROXY_TOKEN_ENV} is not set in the environment"
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as e:
        raise AgentProxyUnavailable(f"transport error reaching proxy: {e}") from e

    if response.status_code in (401, 403):
        raise AgentProxyAuthFailed(
            f"proxy rejected token: status {response.status_code}"
        )
    if response.status_code == 429:
        raise AgentProxyRateLimited("proxy rate-limited this PR")
    if response.status_code == 503:
        raise AgentProxyUnavailable("proxy kill switch is on, agents paused")
    if not (200 <= response.status_code < 300):  # noqa: PLR2004
        raise AgentProxyUnavailable(
            f"proxy returned unexpected status {response.status_code}"
        )

    try:
        payload = response.json()
        choice = payload["choices"][0]
        content = choice["message"]["content"]
        usage = payload.get("usage", {}) or {}
        return ProxyResponse(
            content=content,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise AgentProxyUnavailable(
            f"proxy returned unexpected response shape: {e}"
        ) from e
