"""In-memory ring buffer holding the recent :class:`TurnRecord` history.

A simple bounded deque with a monotonic turn counter. The metrics tab
queries this buffer to render the per-turn pyramid, the cumulative
trajectory, and the asymmetry scatter. The projection calculator queries
it to fit rolling-window coefficients.

No database. No persistence. Refreshing the page or restarting the app
forgets — that's intentional, keeps the deploy story simple and avoids a
backup story for student session data.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Iterable

from core.observability.records import (
    DEFAULT_RING_BUFFER_SIZE,
    TimingSnapshot,
    TokenFlowSnapshot,
    TurnRecord,
)
from core.timing import TimingRecord


class RingBuffer:
    """Bounded thread-safe ring buffer of :class:`TurnRecord` rows.

    Append-only public surface plus snapshot reads. The lock is a plain
    :class:`threading.Lock` since records are small and the operations
    inside the critical section are O(1). Suitable for concurrent FastAPI
    handlers.

    The buffer also exposes a callable suitable for passing to
    :func:`core.timing.set_emitter` so timing records flow in
    automatically without explicit wiring at every chat handler.
    """

    def __init__(self, capacity: int = DEFAULT_RING_BUFFER_SIZE) -> None:
        """Create a buffer with the given maximum row capacity.

        Args:
            capacity: Maximum number of :class:`TurnRecord` rows to retain.
                Older rows are discarded when the buffer is full.
        """
        self._capacity = capacity
        self._records: deque[TurnRecord] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._next_index = 0
        self._pending_flow: dict[str, TokenFlowSnapshot] = {}

    @property
    def capacity(self) -> int:
        """Maximum number of rows the buffer will retain."""
        return self._capacity

    def __len__(self) -> int:
        """Current number of rows held."""
        with self._lock:
            return len(self._records)

    # ─── flow + timing arrival paths ──────────────────────────────────────

    def submit_flow(self, request_id: str, flow: TokenFlowSnapshot) -> None:
        """Stash the token flow snapshot for an in-flight request.

        The chat handler calls this once it knows the per-slot token counts
        and the final output token count. The matching :class:`TimingRecord`
        will arrive later via :meth:`accept_timing_record` (the timing
        emitter callback) — this method holds the flow data until then.

        Args:
            request_id: Identifier shared with the corresponding
                :class:`core.timing.TimingRecord`.
            flow: The fully populated token flow snapshot for this turn.
        """
        with self._lock:
            self._pending_flow[request_id] = flow

    def accept_timing_record(self, record: TimingRecord) -> None:
        """Receive a TimingRecord from core.timing's emitter callback.

        Pairs the timing record with the previously submitted token flow
        snapshot (if any) and appends a complete :class:`TurnRecord` to the
        ring. If no matching flow was submitted (e.g., the request failed
        before flow accounting), a zero-flow placeholder is used so the
        timing data is still visible in the dashboard's timing panel.

        This method is the target of :func:`core.timing.set_emitter`.
        """
        timing_snap = TimingSnapshot(
            build_request_ns=record.build_request_ns,
            network_out_ns=record.network_out_ns,
            prefill_ns=record.prefill_ns,
            decode_ns=record.decode_ns,
            network_back_ns=record.network_back_ns,
            total_ns=record.total_ns,
        )
        with self._lock:
            flow = self._pending_flow.pop(record.request_id, _ZERO_FLOW)
            turn = TurnRecord(
                request_id=record.request_id,
                turn_index=self._next_index,
                timestamp_ns=time.time_ns(),
                flow=flow,
                timing=timing_snap,
            )
            self._next_index += 1
            self._records.append(turn)

    # ─── snapshot reads ───────────────────────────────────────────────────

    def snapshot(self) -> tuple[TurnRecord, ...]:
        """Return an immutable copy of the current buffer contents."""
        with self._lock:
            return tuple(self._records)

    def recent(self, n: int) -> tuple[TurnRecord, ...]:
        """Return the n most recent records, oldest first.

        Args:
            n: How many recent records to fetch. If the buffer holds fewer,
                returns whatever is available.
        """
        if n <= 0:
            return ()
        with self._lock:
            if n >= len(self._records):
                return tuple(self._records)
            return tuple(list(self._records)[-n:])

    def latest(self) -> TurnRecord | None:
        """Return the most recent record, or None if the buffer is empty."""
        with self._lock:
            return self._records[-1] if self._records else None

    def clear(self) -> None:
        """Drop everything. Used by tests and the ops dashboard's reset button."""
        with self._lock:
            self._records.clear()
            self._pending_flow.clear()
            self._next_index = 0


# Sentinel zero-flow snapshot used when timing arrives without a matching
# flow. Module-level so we don't allocate a new one per orphaned record.
_ZERO_FLOW = TokenFlowSnapshot(
    system_tokens=0,
    persona_tokens=0,
    examples_tokens=0,
    history_tokens=0,
    user_tokens=0,
    output_tokens=0,
)


def aggregate_input_categories(
    records: Iterable[TurnRecord],
) -> dict[str, list[int]]:
    """Roll up per-turn input token contributions into per-category lists.

    Used by the cumulative session trajectory chart. Returns one list per
    labelled slot, in the order the records arrived. The lists are the same
    length as the input record sequence.

    Args:
        records: An iterable of :class:`TurnRecord` rows (typically a
            ring buffer snapshot or a slice).

    Returns:
        A dict with keys ``"system"``, ``"persona"``, ``"examples"``,
        ``"history"``, ``"user"``, ``"output"`` mapping to the per-turn
        contribution lists.
    """
    out: dict[str, list[int]] = {
        "system": [],
        "persona": [],
        "examples": [],
        "history": [],
        "user": [],
        "output": [],
    }
    for r in records:
        out["system"].append(r.flow.system_tokens)
        out["persona"].append(r.flow.persona_tokens)
        out["examples"].append(r.flow.examples_tokens)
        out["history"].append(r.flow.history_tokens)
        out["user"].append(r.flow.user_tokens)
        out["output"].append(r.flow.output_tokens)
    return out
