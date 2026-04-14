"""Locked instructor-only ops dashboard for the wize73 class chatbot.

Mounted by the main FastAPI app as a sub-app at ``/ops``. Gated by
Cloudflare Access in production (instructor email allow-list only) and
by an ``OPS_BEARER_TOKEN`` for non-browser clients like the Claude Code
session that ``curl``s the events feed for co-monitoring.

Public surface:

* :func:`create_ops_app` — build the FastAPI sub-app, returns a
  ``FastAPI`` instance ready to be mounted at ``/ops``.
* :class:`OpsState` — singleton holder for the event stream and kill
  switch manager.
* :class:`Event`, :class:`EventSeverity`, :class:`EventStream` — the
  event records and the in-memory bounded ring buffer with async pub/sub.
* :class:`KillSwitch`, :class:`KillSwitchManager`, :class:`SwitchState` —
  the four kill switches the instructor can flip during class.
* :func:`require_ops_auth` — FastAPI dependency that enforces Cloudflare
  Access headers or bearer-token auth.

The HTML dashboard template lives in a follow-up commit alongside the
chatbot UI in task #11. This commit ships JSON + SSE only.
"""

from core.ops.app import (
    IngestEventRequest,
    OpsState,
    SetSwitchRequest,
    create_ops_app,
)
from core.ops.auth import require_ops_auth
from core.ops.events import (
    DEFAULT_EVENT_CAPACITY,
    KNOWN_SOURCES,
    Event,
    EventSeverity,
    EventStream,
)
from core.ops.kill_switches import KillSwitch, KillSwitchManager, SwitchState

__all__ = [
    "DEFAULT_EVENT_CAPACITY",
    "KNOWN_SOURCES",
    "Event",
    "EventSeverity",
    "EventStream",
    "IngestEventRequest",
    "KillSwitch",
    "KillSwitchManager",
    "OpsState",
    "SetSwitchRequest",
    "SwitchState",
    "create_ops_app",
    "require_ops_auth",
]
