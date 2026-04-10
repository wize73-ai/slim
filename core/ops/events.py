"""Event records and the in-memory event stream for the instructor dashboard.

Events are everything that happens during class that the instructor needs
to see live: PR opened, agent failed, deploy succeeded, firewall dropped a
packet, agent 9 flagged malicious code. They flow into a bounded in-memory
stream and fan out to subscribers via per-connection async queues for the
SSE stream endpoint.

No persistence. The buffer is in-memory only and refreshing the page
forgets — that's intentional. A separate append-only JSON dump for post-
class review can be enabled by setting ``OPS_EVENT_LOG_PATH``.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Final


class EventSeverity(str, Enum):
    """Severity bands for the dashboard's row coloring.

    String values so the SSE stream can serialise them directly without
    a custom encoder.

    * ``INFO`` — green. Routine activity. PR opened, agent passed,
      deploy succeeded.
    * ``WARNING`` — yellow. Worth noticing but not blocking. Single
      agent failure, elevated host CPU, slow guapo response.
    * ``ERROR`` — red. Action probably required. Deploy failed,
      repeated agent failures, chat error spike.
    * ``CRITICAL`` — red banner + audio cue. Stop and look. Agent 9
      malice flag, firewall drop, panic stop activated.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# Event source identifiers used by external collectors when ingesting.
# These let the dashboard filter and color by source as well as severity.
KNOWN_SOURCES: Final[frozenset[str]] = frozenset(
    {
        "github",         # PR / commit / merge webhooks
        "agent",          # PR-agent results from the 9 workflows
        "deploy",         # CI deploy workflow + slim deploy.sh
        "firewall",       # nftables drop log tail
        "agent-proxy",    # CI inference proxy call log
        "guapo",          # guapo health probe transitions
        "host",           # slim host stat anomalies
        "chat",           # app container chat error events
        "ops",            # ops dashboard internal events (kill switch flips)
    }
)


@dataclass(frozen=True, slots=True)
class Event:
    """One observable thing that happened.

    Events are immutable after construction. The ``payload`` is a small
    dict of supplementary key-value pairs (typed as ``str`` for safe JSON
    serialisation in the SSE stream — collectors should stringify
    structured values before posting).
    """

    id: str
    timestamp_ns: int
    severity: EventSeverity
    source: str
    kind: str
    summary: str
    payload: dict[str, str] = field(default_factory=dict)

    @classmethod
    def now(
        cls,
        *,
        severity: EventSeverity,
        source: str,
        kind: str,
        summary: str,
        payload: dict[str, str] | None = None,
    ) -> Event:
        """Convenience constructor that fills in id and timestamp.

        Args:
            severity: One of the :class:`EventSeverity` bands.
            source: Origin of the event. Use one of :data:`KNOWN_SOURCES`
                or a new string if appropriate (the dashboard will accept
                any source but unknown ones get a default color).
            kind: Short machine-readable event type, e.g. ``"pr_opened"``,
                ``"deploy_failed"``, ``"firewall_drop"``.
            summary: One-line human-readable description for the dashboard
                row. Keep it under ~120 characters so it fits.
            payload: Optional extra context as flat string key-values.
        """
        return cls(
            id=uuid.uuid4().hex,
            timestamp_ns=time.time_ns(),
            severity=severity,
            source=source,
            kind=kind,
            summary=summary,
            payload=dict(payload) if payload else {},
        )

    def to_json_dict(self) -> dict[str, object]:
        """Serialise to a JSON-safe dict for the API responses and SSE stream."""
        return {
            "id": self.id,
            "timestamp_ns": self.timestamp_ns,
            "severity": self.severity.value,
            "source": self.source,
            "kind": self.kind,
            "summary": self.summary,
            "payload": self.payload,
        }


# Default event buffer capacity. 500 is enough for a 2.5-hour class with
# moderate activity (PR open + 9 agent results + merge + deploy ≈ 12 events
# per cycle, ~40 cycles = 480 events). Older events are evicted FIFO.
DEFAULT_EVENT_CAPACITY: Final[int] = 500

# How big each subscriber's per-connection queue can grow before
# back-pressure starts dropping events for that subscriber. Other
# subscribers (and the central buffer) are unaffected.
_SUBSCRIBER_QUEUE_SIZE: Final[int] = 64


class EventStream:
    """In-memory bounded event buffer with async pub/sub for SSE subscribers.

    Append is synchronous and non-blocking. Subscribers are async iterators
    that consume from a per-connection queue; if a subscriber is slow and
    its queue fills up, new events for that subscriber are silently dropped
    (never blocking the central stream). Other subscribers and the
    history buffer are unaffected.
    """

    def __init__(self, capacity: int = DEFAULT_EVENT_CAPACITY) -> None:
        """Build an empty event stream with the given capacity."""
        self._capacity = capacity
        self._buffer: deque[Event] = deque(maxlen=capacity)
        self._subscribers: list[asyncio.Queue[Event]] = []

    @property
    def capacity(self) -> int:
        """Maximum number of events the buffer retains."""
        return self._capacity

    def __len__(self) -> int:
        """Current number of events in the history buffer."""
        return len(self._buffer)

    def append(self, event: Event) -> None:
        """Add an event to the buffer and fan out to subscribers.

        Subscriber queues that are full (back-pressured slow consumer)
        silently drop the new event. The central buffer always retains.
        Synchronous and non-blocking.
        """
        self._buffer.append(event)
        # Iterate over a copy so concurrent subscribe/unsubscribe is safe.
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def snapshot(self) -> tuple[Event, ...]:
        """Return an immutable copy of all events currently buffered."""
        return tuple(self._buffer)

    def recent(self, n: int) -> tuple[Event, ...]:
        """Return the n most recent events, oldest first.

        If the buffer holds fewer than ``n``, returns whatever is available.
        ``n <= 0`` returns an empty tuple.
        """
        if n <= 0:
            return ()
        if n >= len(self._buffer):
            return tuple(self._buffer)
        return tuple(list(self._buffer)[-n:])

    def filter_by_source(self, source: str) -> tuple[Event, ...]:
        """Return all buffered events from a single source identifier."""
        return tuple(e for e in self._buffer if e.source == source)

    def filter_by_severity(self, severity: EventSeverity) -> tuple[Event, ...]:
        """Return all buffered events at the given severity level."""
        return tuple(e for e in self._buffer if e.severity == severity)

    def clear(self) -> None:
        """Drop the entire buffer. Used by tests and the ops reset action."""
        self._buffer.clear()

    # ─── async pub/sub for the SSE stream ─────────────────────────────────

    def subscribe(self) -> asyncio.Queue[Event]:
        """Register a new subscriber and return its dedicated queue.

        The caller is responsible for calling :meth:`unsubscribe` when the
        connection closes (typically in a ``try``/``finally`` around the
        SSE generator). Subscribers receive *new* events from the moment
        of subscription onward — to also surface history, the SSE handler
        should yield :meth:`snapshot` first before consuming the queue.
        """
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        """Remove a subscriber's queue from the fan-out list.

        Idempotent — calling on an already-removed queue is a no-op.
        """
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    @property
    def subscriber_count(self) -> int:
        """Number of currently-connected SSE subscribers."""
        return len(self._subscribers)
