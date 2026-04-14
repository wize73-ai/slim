"""GuapoStatsProvider — what we can learn about guapo without patching it.

Two implementations behind a common shape so the metrics tab can swap
between them with a single config flag:

* :class:`IndirectProvider` — the default. Uses only the frozen guapo
  surface (``/healthz``, ``/v1/models``, plus the most recent real chat
  call's TTFT and decode rate). Background-polls health to compute a
  rolling RTT stddev that proxies for "guapo is busy serving someone."
  This is what we ship now per the user's decision not to patch guapo.

* :class:`DirectProvider` — a stub. Ready for the day guapo gets a
  ``/v1/stats`` endpoint that exposes a sanitised allowlist of GPU and
  host metrics. The stub raises ``NotImplementedError`` to make it
  obvious if it gets selected by accident.

Both implementations return :class:`GuapoIndirectStats` so upstream
consumers (the metrics tab JSON endpoint, the projection coefficient
fitter) don't need to know which provider is in use.
"""

from __future__ import annotations

import os
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Final, Protocol

from core.observability.records import GuapoIndirectStats

# How many seconds of health-RTT history to keep in the rolling window.
# 60 seconds gives the chat-queue-signal calculator a meaningful denominator
# without consuming much memory.
_HEALTH_WINDOW_SECONDS: Final[int] = 60

# Minimum samples needed before computing the rolling stddev. Below this we
# return None for the chat-queue-signal so the dashboard can show "warming up".
_MIN_SAMPLES_FOR_STDDEV: Final[int] = 5


class GuapoStatsProvider(Protocol):
    """Common shape for any provider returning guapo stats.

    Implementations must be safe to call from concurrent FastAPI handlers.
    """

    async def fetch(self) -> GuapoIndirectStats:
        """Return the current snapshot of guapo stats."""
        ...

    async def record_chat_call(
        self,
        ttft_ms: float,
        decode_tok_per_sec: float,
    ) -> None:
        """Pass a real chat call's TTFT and decode rate into the provider.

        Used by the chat handler so the indirect provider can show the
        most recent measured values without polling for them.
        """
        ...


@dataclass
class _HealthSample:
    """One health-probe RTT measurement."""

    timestamp: float
    rtt_ms: float | None  # None if the probe failed
    healthy: bool
    whisper_loaded: bool
    tts_loaded: bool


@dataclass
class IndirectProvider:
    """Inference-only guapo stats from the frozen interface.

    Configures itself from environment:
        OPENAI_BASE_URL: required, the same value the chat client uses

    Background polls ``/healthz`` and ``/v1/models``. Records the rolling
    RTT and computes a stddev as a proxy for "guapo is busy serving
    someone right now." Receives the most recent chat call's TTFT and
    decode rate via :meth:`record_chat_call` so those numbers can appear
    in the dashboard without yet another poll.

    No threads, no background tasks at construction time — call
    :meth:`start_background_polling` after the FastAPI app starts up if
    you want continuous polling. Call :meth:`fetch` on demand to grab
    the current snapshot.
    """

    base_url: str
    _samples: deque[_HealthSample] = field(default_factory=lambda: deque(maxlen=64))
    _last_chat_ttft_ms: float | None = None
    _last_chat_decode_tok_per_sec: float | None = None
    _models_count: int = 0

    @classmethod
    def from_env(cls) -> IndirectProvider:
        """Build an IndirectProvider from the OPENAI_BASE_URL env var."""
        return cls(base_url=os.environ["OPENAI_BASE_URL"])

    async def fetch(self) -> GuapoIndirectStats:
        """Return a snapshot computed from the rolling samples + chat history.

        Performs one synchronous health probe so the snapshot reflects the
        very latest state. Falls back gracefully when the request fails —
        the snapshot then reports ``healthy=False`` and the model-loaded
        flags reflect the last known good values.
        """
        await self._probe_once()
        return self._build_snapshot()

    async def record_chat_call(
        self,
        ttft_ms: float,
        decode_tok_per_sec: float,
    ) -> None:
        """Record telemetry from a real chat completion."""
        self._last_chat_ttft_ms = ttft_ms
        self._last_chat_decode_tok_per_sec = decode_tok_per_sec

    # ─── implementation ──────────────────────────────────────────────────

    async def _probe_once(self) -> None:
        """Hit /healthz and /v1/models, append a sample.

        Lazily imports httpx so this module is importable without httpx
        present (e.g., during unit tests of the projection layer).
        """
        # Lazy import keeps the module importable in test contexts.
        import httpx  # noqa: PLC0415

        sample_time = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                start = time.monotonic()
                health_resp = await client.get(f"{self.base_url}/../healthz")
                rtt_ms = (time.monotonic() - start) * 1000
                if health_resp.status_code == 200:  # noqa: PLR2004
                    body = health_resp.json()
                    healthy = True
                    whisper_loaded = bool(body.get("whisper_loaded", False))
                    tts_loaded = bool(body.get("tts_loaded", False))
                else:
                    healthy = False
                    whisper_loaded = False
                    tts_loaded = False

                # Models count, best-effort. Doesn't fail the probe if it errors.
                try:
                    models_resp = await client.get(f"{self.base_url}/models")
                    if models_resp.status_code == 200:  # noqa: PLR2004
                        models_body = models_resp.json()
                        data = models_body.get("data", [])
                        self._models_count = len(data) if isinstance(data, list) else 0
                except (httpx.HTTPError, ValueError):
                    pass
        except (httpx.HTTPError, ValueError):
            rtt_ms = None
            healthy = False
            whisper_loaded = False
            tts_loaded = False

        self._samples.append(
            _HealthSample(
                timestamp=sample_time,
                rtt_ms=rtt_ms,
                healthy=healthy,
                whisper_loaded=whisper_loaded,
                tts_loaded=tts_loaded,
            )
        )

    def _build_snapshot(self) -> GuapoIndirectStats:
        """Compute the snapshot fields from the rolling sample window."""
        if not self._samples:
            return GuapoIndirectStats(
                healthy=False,
                whisper_loaded=False,
                tts_loaded=False,
                health_rtt_ms_60s_avg=None,
                health_rtt_ms_60s_stddev=None,
                last_chat_ttft_ms=self._last_chat_ttft_ms,
                last_chat_decode_tok_per_sec=self._last_chat_decode_tok_per_sec,
                models_available=self._models_count,
            )

        latest = self._samples[-1]
        cutoff = latest.timestamp - _HEALTH_WINDOW_SECONDS
        recent_rtts = [
            s.rtt_ms for s in self._samples if s.timestamp >= cutoff and s.rtt_ms is not None
        ]

        avg_rtt: float | None
        stddev_rtt: float | None
        avg_rtt = statistics.mean(recent_rtts) if len(recent_rtts) >= 1 else None
        if len(recent_rtts) >= _MIN_SAMPLES_FOR_STDDEV:
            stddev_rtt = statistics.pstdev(recent_rtts)
        else:
            stddev_rtt = None

        return GuapoIndirectStats(
            healthy=latest.healthy,
            whisper_loaded=latest.whisper_loaded,
            tts_loaded=latest.tts_loaded,
            health_rtt_ms_60s_avg=avg_rtt,
            health_rtt_ms_60s_stddev=stddev_rtt,
            last_chat_ttft_ms=self._last_chat_ttft_ms,
            last_chat_decode_tok_per_sec=self._last_chat_decode_tok_per_sec,
            models_available=self._models_count,
        )


class DirectProvider:
    """Stub for a future ``/v1/stats`` endpoint on guapo.

    Per the user's decision not to patch guapo at this time, this provider
    is intentionally unimplemented. The shape exists so when/if guapo gets
    a stats endpoint, swapping in a real implementation requires only
    flipping a config flag — no upstream code changes.
    """

    def __init__(self, base_url: str) -> None:
        """Construct a stub DirectProvider that raises on use."""
        self.base_url = base_url

    async def fetch(self) -> GuapoIndirectStats:
        """Always raises: this provider is a placeholder."""
        raise NotImplementedError(
            "DirectProvider requires a /v1/stats endpoint on guapo, "
            "which has not been added per project decision 2026-04-10. "
            "Use IndirectProvider until then."
        )

    async def record_chat_call(
        self,
        ttft_ms: float,  # noqa: ARG002
        decode_tok_per_sec: float,  # noqa: ARG002
    ) -> None:
        """No-op stub."""
        return
