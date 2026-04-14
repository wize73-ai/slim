"""Per-request timing instrumentation feeding the observability ring buffer.

Records six timestamps per chat handler invocation:

============  ===================================================
``t0``        Enter handler — set automatically by ``Instrument``
``t1``        ``build_request()`` done — user calls ``mark("t1")``
``t2``        First byte sent to guapo — user calls ``mark("t2")``
``t3``        First SSE chunk back from guapo (= prefill done)
``t4``        Last SSE chunk from guapo (= decode done)
``t5``        Last byte to client — set automatically on exit
============  ===================================================

The intervals between markers feed the bidirectional metrics on the
``/metrics`` tab — pre-vs-post processing time, prefill-vs-decode latency,
and the cumulative session trajectory.

Usage::

    from core.timing import instrument


    async def chat_handler(request):
        with instrument() as t:
            messages = build_request(...)
            t.mark("t1")
            async for chunk in stream_completion(messages, t):
                yield chunk
            # t5 is set automatically when the with-block exits

The :class:`Instrument` context manager emits a :class:`TimingRecord` on
exit through the registered emitter callback. ``core.observability`` calls
:func:`set_emitter` at startup to plug in its ring buffer; modules without
observability registered (e.g., during tests) silently discard records.

Both the synchronous (``with``) and asynchronous (``async with``) context
manager protocols are supported. Use whichever your handler uses.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Literal

__all__ = [
    "Instrument",
    "TimingMark",
    "TimingRecord",
    "instrument",
    "set_emitter",
]


TimingMark = Literal["t1", "t2", "t3", "t4"]
"""User-settable timing marker labels.

``t0`` and ``t5`` are set automatically by :class:`Instrument` and are not
included here so the type checker prevents accidentally re-marking them.
"""


@dataclass(frozen=True, slots=True)
class TimingRecord:
    """Captured per-request timing data with computed duration properties.

    All timestamps are monotonic nanoseconds (``time.monotonic_ns()``). Any
    intermediate marker may be ``None`` if that point in the request lifecycle
    never happened — for example if the request failed before guapo was reached,
    ``t2`` and beyond will all be ``None``. The duration properties handle this
    gracefully by also returning ``None``.

    Duration properties expose the bidirectional pairs the metrics tab needs:

    ====================  ==========================  ============================
    Property              Interval                    What it represents
    ====================  ==========================  ============================
    ``build_request_ns``  ``t0 → t1``                 Pre-processing on our side
    ``network_out_ns``    ``t1 → t2``                 Send latency to guapo
    ``prefill_ns``        ``t2 → t3``                 Guapo prefill (input tokens)
    ``decode_ns``         ``t3 → t4``                 Guapo decode (output tokens)
    ``network_back_ns``   ``t4 → t5``                 Render / send-back to client
    ``total_ns``          ``t0 → t5``                 End-to-end wall time
    ====================  ==========================  ============================
    """

    request_id: str
    t0_handler_enter_ns: int
    t1_build_request_done_ns: int | None
    t2_first_byte_out_ns: int | None
    t3_first_sse_chunk_in_ns: int | None
    t4_last_sse_chunk_in_ns: int | None
    t5_handler_exit_ns: int

    @property
    def build_request_ns(self) -> int | None:
        """Time spent constructing the messages array (``t0 → t1``)."""
        if self.t1_build_request_done_ns is None:
            return None
        return self.t1_build_request_done_ns - self.t0_handler_enter_ns

    @property
    def network_out_ns(self) -> int | None:
        """Time from build done to first byte sent to guapo (``t1 → t2``)."""
        if self.t1_build_request_done_ns is None or self.t2_first_byte_out_ns is None:
            return None
        return self.t2_first_byte_out_ns - self.t1_build_request_done_ns

    @property
    def prefill_ns(self) -> int | None:
        """Guapo prefill time: first byte out → first SSE chunk in (``t2 → t3``).

        This is approximately TTFT (time to first token) minus network round
        trip. Dominated by input token count and the model's prefill compute
        characteristics.
        """
        if self.t2_first_byte_out_ns is None or self.t3_first_sse_chunk_in_ns is None:
            return None
        return self.t3_first_sse_chunk_in_ns - self.t2_first_byte_out_ns

    @property
    def decode_ns(self) -> int | None:
        """Guapo decode time: streaming generation (``t3 → t4``).

        Dominated by output token count. Combined with token count this gives
        the per-decode tok/sec rate the projection calculator uses.
        """
        if self.t3_first_sse_chunk_in_ns is None or self.t4_last_sse_chunk_in_ns is None:
            return None
        return self.t4_last_sse_chunk_in_ns - self.t3_first_sse_chunk_in_ns

    @property
    def network_back_ns(self) -> int | None:
        """Time from last SSE chunk in to last byte to client (``t4 → t5``)."""
        if self.t4_last_sse_chunk_in_ns is None:
            return None
        return self.t5_handler_exit_ns - self.t4_last_sse_chunk_in_ns

    @property
    def total_ns(self) -> int:
        """End-to-end wall time (``t0 → t5``)."""
        return self.t5_handler_exit_ns - self.t0_handler_enter_ns


# ────────────────────────────────────────────────────────────────────────────
# Emitter callback registry. Loose coupling between timing and observability:
# observability registers its ring buffer's append at startup, timing emits
# records on context exit. No circular import.
# ────────────────────────────────────────────────────────────────────────────

_emitter: Callable[[TimingRecord], None] | None = None


def set_emitter(emitter: Callable[[TimingRecord], None] | None) -> None:
    """Register a callback to receive every :class:`TimingRecord` on exit.

    Pass ``None`` to disable emission, which is useful in tests where you
    want to construct an :class:`Instrument` without side effects on a real
    observability buffer.

    The emitter is called synchronously from :meth:`Instrument.__exit__` —
    keep it cheap. The standard implementation in
    :mod:`core.observability` is an in-memory ring buffer append, which is
    O(1).

    Args:
        emitter: Callable taking a single :class:`TimingRecord`, or ``None``
            to clear any previously-registered emitter.
    """
    global _emitter  # noqa: PLW0603 — module-level registry is intentional
    _emitter = emitter


def _emit(record: TimingRecord) -> None:
    """Dispatch a record to the registered emitter, if any.

    No-op when no emitter is registered, which is the case during tests
    and any startup phase before observability has wired itself in.
    """
    if _emitter is not None:
        _emitter(record)


# ────────────────────────────────────────────────────────────────────────────
# Instrument — the context manager users interact with.
# ────────────────────────────────────────────────────────────────────────────


class Instrument:
    """Context manager that records per-request timing markers.

    ``t0`` (handler enter) is set automatically when the context is entered.
    ``t5`` (handler exit) is set automatically when the context is exited.
    Intermediate marks ``t1`` through ``t4`` are set by calling :meth:`mark`
    at the appropriate points in the request handler.

    On exit, a :class:`TimingRecord` is built from the captured marks and
    dispatched to the registered emitter (set by ``core.observability`` at
    startup). Both synchronous (``with``) and asynchronous (``async with``)
    context manager protocols are supported.

    Example::

        async def chat_handler(request):
            with instrument() as t:
                messages = build_request(...)
                t.mark("t1")
                async for chunk in stream_completion(messages, t):
                    yield chunk
                # t5 is set automatically when this with-block exits

    The same ``t`` instance is typically threaded through downstream calls
    so they can record their own markers — for example
    ``stream_completion`` would call ``t.mark("t2")`` right before sending
    bytes to guapo and ``t.mark("t3")`` on receiving the first SSE chunk.
    """

    __slots__ = ("_marks", "request_id")

    def __init__(self, request_id: str | None = None) -> None:
        """Create an Instrument and capture ``t0`` immediately.

        Args:
            request_id: Optional caller-supplied identifier to associate with
                the resulting :class:`TimingRecord`. If omitted, a random
                UUID4 hex is generated. Useful when correlating timing data
                with chat session logs.
        """
        self.request_id = request_id or uuid.uuid4().hex
        self._marks: dict[str, int] = {"t0": time.monotonic_ns()}

    def mark(self, label: TimingMark) -> None:
        """Record the current monotonic time at the named intermediate marker.

        Calling :meth:`mark` more than once with the same label simply
        overwrites the prior timestamp — the most recent call wins.

        Args:
            label: One of ``"t1"``, ``"t2"``, ``"t3"``, ``"t4"``. The
                literal type is enforced by mypy so typos won't compile.
        """
        self._marks[label] = time.monotonic_ns()

    def __enter__(self) -> Instrument:
        """Enter the synchronous context. ``t0`` is already set in ``__init__``."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Set ``t5``, build the :class:`TimingRecord`, and dispatch to the emitter.

        Always emits, even when an exception is propagating, so failed
        requests still appear in the metrics tab as partial records. The
        exception is not suppressed.
        """
        self._marks["t5"] = time.monotonic_ns()
        record = TimingRecord(
            request_id=self.request_id,
            t0_handler_enter_ns=self._marks["t0"],
            t1_build_request_done_ns=self._marks.get("t1"),
            t2_first_byte_out_ns=self._marks.get("t2"),
            t3_first_sse_chunk_in_ns=self._marks.get("t3"),
            t4_last_sse_chunk_in_ns=self._marks.get("t4"),
            t5_handler_exit_ns=self._marks["t5"],
        )
        _emit(record)

    async def __aenter__(self) -> Instrument:
        """Asynchronous flavor of :meth:`__enter__` for use with ``async with``."""
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Asynchronous flavor of :meth:`__exit__` for use with ``async with``."""
        self.__exit__(exc_type, exc_val, exc_tb)


def instrument(request_id: str | None = None) -> Instrument:
    """Convenience factory that returns a fresh :class:`Instrument` context.

    Slightly more readable than calling the class directly:

    .. code-block:: python

        with instrument() as t:
            ...

    versus

    .. code-block:: python

        with Instrument() as t:
            ...

    Args:
        request_id: Optional request identifier passed straight through to
            :class:`Instrument`. If omitted, a UUID4 hex is generated.

    Returns:
        A new :class:`Instrument` ready to be used as a context manager.
    """
    return Instrument(request_id=request_id)
