"""FastAPI sub-app for the instructor /ops dashboard.

Mounted by the main app at ``/ops``. Cloudflare Access in front gates
browser traffic to the instructor's email only; the bearer token path
covers non-browser clients (notably Claude curl). Both layers configured
in :mod:`core.ops.auth`.

JSON endpoints + an SSE event stream in this commit. The HTML dashboard
template lives in a follow-up commit alongside the chatbot UI.

Endpoints:

* ``GET  /ops/healthz`` — liveness for the sub-app
* ``GET  /ops/events`` — recent events as JSON, optionally filtered
* ``GET  /ops/events.json`` — alias of ``/ops/events`` for Claude curl
* ``GET  /ops/events/stream`` — Server-Sent Events live feed
* ``POST /ops/events`` — ingest a new event from a collector
* ``GET  /ops/switches`` — current state of all kill switches (peek)
* ``POST /ops/switches/{name}/flip`` — toggle a switch
* ``POST /ops/switches/{name}/set`` — force a switch to a value
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Path
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from core.ops.auth import require_ops_auth
from core.ops.events import (
    DEFAULT_EVENT_CAPACITY,
    Event,
    EventSeverity,
    EventStream,
)
from core.ops.kill_switches import KillSwitch, KillSwitchManager


class OpsState:
    """Holds the singletons the routes close over.

    A simple object instead of FastAPI ``app.state`` so it's testable
    without spinning up a real app.
    """

    def __init__(
        self,
        *,
        events: EventStream | None = None,
        switches: KillSwitchManager | None = None,
    ) -> None:
        """Construct the state container with optional overrides."""
        self.events = events or EventStream(capacity=DEFAULT_EVENT_CAPACITY)
        self.switches = switches or KillSwitchManager()


# ────────────────────────────────────────────────────────────────────────────
# Request models for the POST endpoints (Pydantic input validation)
# ────────────────────────────────────────────────────────────────────────────


class IngestEventRequest(BaseModel):
    """Body shape for ``POST /ops/events``."""

    severity: EventSeverity
    source: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=512)
    payload: dict[str, str] = Field(default_factory=dict)


class SetSwitchRequest(BaseModel):
    """Body shape for ``POST /ops/switches/{name}/set``."""

    active: bool


# ────────────────────────────────────────────────────────────────────────────
# Sub-app factory
# ────────────────────────────────────────────────────────────────────────────


def create_ops_app(state: OpsState | None = None) -> FastAPI:
    """Build the ops FastAPI sub-app.

    Args:
        state: Optional pre-built :class:`OpsState`. If omitted, a default
            is constructed with fresh empty event stream + kill switches.

    Returns:
        A FastAPI instance ready to be mounted at ``/ops``.
    """
    if state is None:
        state = OpsState()

    ops_app = FastAPI(title="ops", docs_url=None, redoc_url=None)

    # ─── liveness ─────────────────────────────────────────────────────────

    @ops_app.get("/healthz")
    async def healthz() -> dict[str, object]:
        """Liveness probe for the ops sub-app itself.

        Unauthenticated so external watchdogs can probe it without needing
        a token. Reveals nothing sensitive — just buffer size and
        subscriber count.
        """
        return {
            "status": "ok",
            "events_buffered": len(state.events),
            "events_capacity": state.events.capacity,
            "subscribers": state.events.subscriber_count,
        }

    # ─── events: read endpoints (auth required) ───────────────────────────

    @ops_app.get("/events")
    async def get_events(
        identity: Annotated[str, Depends(require_ops_auth)],
        limit: int = 100,
        source: str | None = None,
        severity: EventSeverity | None = None,
    ) -> dict[str, Any]:
        """Return recent events as JSON, optionally filtered.

        Args:
            limit: Maximum number of events to return (default 100).
            source: Optional source filter (e.g. ``"firewall"``).
            severity: Optional severity filter (e.g. ``"critical"``).
        """
        # Identity is consumed by the dependency for auth; not logged here.
        del identity
        events: tuple[Event, ...] = state.events.snapshot()
        if source is not None:
            events = tuple(e for e in events if e.source == source)
        if severity is not None:
            events = tuple(e for e in events if e.severity == severity)
        if limit > 0 and len(events) > limit:
            events = events[-limit:]
        return {
            "count": len(events),
            "capacity": state.events.capacity,
            "events": [e.to_json_dict() for e in events],
        }

    @ops_app.get("/events.json")
    async def get_events_json(
        identity: Annotated[str, Depends(require_ops_auth)],
        limit: int = 100,
    ) -> dict[str, Any]:
        """Alias of /events for Claude curl convenience (no query params)."""
        return await get_events(identity=identity, limit=limit)

    @ops_app.get("/events/stream")
    async def stream_events(
        identity: Annotated[str, Depends(require_ops_auth)],
    ) -> EventSourceResponse:
        """Server-Sent Events live stream.

        Yields all currently-buffered events first (as a snapshot), then
        every new event as it arrives. The connection stays open until the
        client disconnects.

        Heartbeat ``ping`` events are sent every 15s automatically by
        sse-starlette to keep proxies from timing the connection out.
        """
        del identity

        async def event_generator() -> AsyncIterator[dict[str, Any]]:
            # Replay buffered history first.
            for e in state.events.snapshot():
                yield {"event": "event", "data": e.to_json_dict(), "id": e.id}

            # Subscribe and stream new events.
            queue = state.events.subscribe()
            try:
                while True:
                    e = await queue.get()
                    yield {"event": "event", "data": e.to_json_dict(), "id": e.id}
            except asyncio.CancelledError:
                # Client disconnected. Clean up subscriber.
                raise
            finally:
                state.events.unsubscribe(queue)

        return EventSourceResponse(event_generator(), ping=15)

    # ─── events: ingest endpoint (auth required) ──────────────────────────

    @ops_app.post("/events", status_code=201)
    async def ingest_event(
        req: IngestEventRequest,
        identity: Annotated[str, Depends(require_ops_auth)],
    ) -> dict[str, str]:
        """Ingest a new event from an external collector.

        The collector identity (from the bearer token or Cf-Access header)
        is recorded in the event's payload as ``ingest_by`` for the audit
        trail. Returns the new event's id.
        """
        payload = dict(req.payload)
        payload.setdefault("ingest_by", identity)
        event = Event.now(
            severity=req.severity,
            source=req.source,
            kind=req.kind,
            summary=req.summary,
            payload=payload,
        )
        state.events.append(event)
        return {"id": event.id}

    # ─── kill switches (auth required) ────────────────────────────────────

    @ops_app.get("/switches")
    async def list_switches(
        identity: Annotated[str, Depends(require_ops_auth)],
    ) -> dict[str, dict[str, object]]:
        """Return the current state of all four kill switches (peek)."""
        del identity
        return state.switches.snapshot()

    @ops_app.post("/switches/{name}/flip")
    async def flip_switch(
        name: Annotated[str, Path(min_length=1)],
        identity: Annotated[str, Depends(require_ops_auth)],
    ) -> dict[str, object]:
        """Toggle the named switch and emit an event recording the flip."""
        try:
            switch = KillSwitch(name)
        except ValueError as e:
            raise HTTPException(
                status_code=404,
                detail=f"unknown kill switch {name!r}",
            ) from e
        new_state = state.switches.flip(switch, by=identity)
        state.events.append(
            Event.now(
                severity=(
                    EventSeverity.WARNING if new_state.active else EventSeverity.INFO
                ),
                source="ops",
                kind="kill_switch_flip",
                summary=(
                    f"{switch.value} -> "
                    f"{'ACTIVE' if new_state.active else 'inactive'} (by {identity})"
                ),
                payload={
                    "switch": switch.value,
                    "active": str(new_state.active).lower(),
                    "set_by": identity,
                },
            )
        )
        return {
            "switch": switch.value,
            "active": new_state.active,
            "set_by": new_state.set_by,
        }

    @ops_app.post("/switches/{name}/set")
    async def set_switch(
        name: Annotated[str, Path(min_length=1)],
        req: SetSwitchRequest,
        identity: Annotated[str, Depends(require_ops_auth)],
    ) -> dict[str, object]:
        """Force a switch to a specific state."""
        try:
            switch = KillSwitch(name)
        except ValueError as e:
            raise HTTPException(
                status_code=404,
                detail=f"unknown kill switch {name!r}",
            ) from e
        new_state = state.switches.set(switch, active=req.active, by=identity)
        state.events.append(
            Event.now(
                severity=(
                    EventSeverity.WARNING if req.active else EventSeverity.INFO
                ),
                source="ops",
                kind="kill_switch_set",
                summary=(
                    f"{switch.value} forced to "
                    f"{'ACTIVE' if req.active else 'inactive'} (by {identity})"
                ),
                payload={
                    "switch": switch.value,
                    "active": str(req.active).lower(),
                    "set_by": identity,
                },
            )
        )
        return {
            "switch": switch.value,
            "active": new_state.active,
            "set_by": new_state.set_by,
        }

    return ops_app
