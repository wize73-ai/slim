"""FastAPI sub-app exposing the metrics endpoints.

Mounted by the main app at ``/metrics`` so it survives any breakage in
the student-editable chatbot router. JSON endpoints only in this commit;
the HTML templates and SVG charts arrive in a follow-up commit alongside
the dumb v1 chatbot UI in task #11.

Endpoints:

* ``GET /metrics/healthz`` — liveness for the metrics sub-app itself
* ``GET /metrics/turns`` — recent ring buffer rows as JSON
* ``GET /metrics/turns/latest`` — most recent turn record
* ``GET /metrics/stats/guapo`` — current guapo indirect snapshot
* ``GET /metrics/stats/slim`` — current slim host snapshot from the sidecar
* ``POST /metrics/projection`` — run a projection from an architecture spec

The sub-app does NOT expose anything that mutates state — it's read-only
plus the projection POST which is a pure function of its inputs.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from core.observability.guapo_provider import GuapoStatsProvider, IndirectProvider
from core.observability.projection import (
    ArchitectureSpec,
    fit_coefficients,
    project,
)
from core.observability.records import TurnRecord
from core.observability.ring_buffer import RingBuffer
from core.observability.slim_stats import SlimStatsClient
from core.timing import set_emitter


class MetricsState:
    """Holds the singletons the routes close over.

    A simple object instead of FastAPI ``app.state`` so it's testable
    without spinning up a real app.
    """

    def __init__(
        self,
        *,
        ring_buffer: RingBuffer,
        guapo_provider: GuapoStatsProvider,
        slim_client: SlimStatsClient,
    ) -> None:
        """Construct the state container."""
        self.ring_buffer = ring_buffer
        self.guapo_provider = guapo_provider
        self.slim_client = slim_client


class ProjectionRequest(BaseModel):
    """Pydantic input shape for the projection POST endpoint."""

    system_tokens: int = Field(ge=0)
    persona_tokens: int = Field(default=0, ge=0)
    few_shot_count: int = Field(default=0, ge=0)
    avg_few_shot_tokens: int = Field(default=0, ge=0)
    history_retention_turns: int = Field(default=0, ge=0)
    avg_user_msg_tokens: int = Field(ge=1)
    avg_assistant_reply_tokens: int = Field(ge=1)
    planned_turns: int = Field(ge=1, le=200)


def create_metrics_app(state: MetricsState | None = None) -> FastAPI:
    """Build the metrics FastAPI sub-app.

    Args:
        state: Optional pre-built :class:`MetricsState`. If omitted, a
            default is constructed from environment (Indirect guapo
            provider, sidecar client from ``SLIM_SIDECAR_URL``).

    Returns:
        A FastAPI instance ready to be mounted at ``/metrics``.
    """
    if state is None:
        state = MetricsState(
            ring_buffer=RingBuffer(),
            guapo_provider=IndirectProvider.from_env(),
            slim_client=SlimStatsClient(),
        )

    # Wire timing into the ring buffer. Done at sub-app build time so
    # importing this module doesn't have side effects.
    set_emitter(state.ring_buffer.accept_timing_record)

    metrics_app = FastAPI(title="metrics", docs_url=None, redoc_url=None)

    @metrics_app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness for the metrics sub-app itself."""
        return {"status": "ok", "buffer_size": str(len(state.ring_buffer))}

    @metrics_app.get("/turns")
    async def get_turns(limit: int = 100) -> dict[str, Any]:
        """Return the most recent ``limit`` turn records as JSON."""
        rows = state.ring_buffer.recent(limit)
        return {
            "count": len(rows),
            "capacity": state.ring_buffer.capacity,
            "turns": [_serialize_turn(r) for r in rows],
        }

    @metrics_app.get("/turns/latest")
    async def get_latest_turn() -> dict[str, Any]:
        """Return the most recent turn record, or 404 if the buffer is empty."""
        latest = state.ring_buffer.latest()
        if latest is None:
            raise HTTPException(status_code=404, detail="no turns recorded yet")
        return _serialize_turn(latest)

    @metrics_app.get("/stats/guapo")
    async def stats_guapo() -> dict[str, Any]:
        """Current guapo indirect snapshot."""
        snap = await state.guapo_provider.fetch()
        return asdict(snap)

    @metrics_app.get("/stats/slim")
    async def stats_slim() -> dict[str, Any]:
        """Current slim host snapshot from the sidecar."""
        snap = await state.slim_client.fetch()
        if snap is None:
            return {"available": False}
        return {"available": True, **asdict(snap)}

    @metrics_app.post("/projection")
    async def projection(req: ProjectionRequest) -> dict[str, Any]:
        """Project per-turn token, FLOPs, and time curves for an arch spec."""
        spec = ArchitectureSpec(
            system_tokens=req.system_tokens,
            persona_tokens=req.persona_tokens,
            few_shot_count=req.few_shot_count,
            avg_few_shot_tokens=req.avg_few_shot_tokens,
            history_retention_turns=req.history_retention_turns,
            avg_user_msg_tokens=req.avg_user_msg_tokens,
            avg_assistant_reply_tokens=req.avg_assistant_reply_tokens,
            planned_turns=req.planned_turns,
        )
        coeffs = fit_coefficients(state.ring_buffer.snapshot())
        result = project(spec, coeffs)
        return {
            "spec": asdict(result.spec),
            "coefficients": asdict(result.coefficients),
            "context_wall_at_turn": result.context_wall_at_turn,
            "turns": [asdict(t) for t in result.turns],
        }

    return metrics_app


def _serialize_turn(turn: TurnRecord) -> dict[str, Any]:
    """Serialise a TurnRecord to JSON-safe dict for the API responses.

    Property fields (input_total, total, asymmetry, ttft_ns) are added
    explicitly because asdict() only walks declared fields.
    """
    return {
        "request_id": turn.request_id,
        "turn_index": turn.turn_index,
        "timestamp_ns": turn.timestamp_ns,
        "flow": {
            **asdict(turn.flow),
            "input_total": turn.flow.input_total,
            "total": turn.flow.total,
            "asymmetry": turn.flow.asymmetry,
        },
        "timing": {
            **asdict(turn.timing),
            "ttft_ns": turn.timing.ttft_ns,
        },
    }
