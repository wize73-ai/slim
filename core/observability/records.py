"""Data records for the observability ring buffer.

These are the structured rows that flow into the metrics tab. Each
:class:`TurnRecord` captures one chat turn end-to-end: which slots had
how many tokens, how the response decomposed, and how long each phase took.

The token-flow side comes from :class:`core.chat.LabelledMessages`. The
timing side comes from :class:`core.timing.TimingRecord`. The output side
is collected by ``stream_completion`` after the stream ends.

All records are immutable frozen dataclasses with computed properties for
the bidirectional pairs the metrics tab visualises.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class TokenFlowSnapshot:
    """Per-turn token decomposition for the pyramid and trajectory charts.

    Tracks the tokens contributed by each labelled slot of the input
    (system / persona / examples / history / user) plus the total output
    token count. Persona is reported separately even though its tokens are
    embedded in the system slot — the metrics tab needs to show "your
    persona costs N tokens per turn" as an isolated line item so students
    can optimise it.
    """

    system_tokens: int
    persona_tokens: int  # already counted inside system_tokens
    examples_tokens: int
    history_tokens: int
    user_tokens: int
    output_tokens: int

    @property
    def input_total(self) -> int:
        """Sum of all input slots that hit the wire (persona excluded — embedded)."""
        return (
            self.system_tokens
            + self.examples_tokens
            + self.history_tokens
            + self.user_tokens
        )

    @property
    def total(self) -> int:
        """Full turn cost: input + output tokens."""
        return self.input_total + self.output_tokens

    @property
    def asymmetry(self) -> float:
        """Output ÷ input ratio. >1 = expansive turn, <1 = compressive turn.

        Used as the y-axis of the input/output asymmetry scatter chart. A
        cooking persona answering "how do I boil an egg" produces a high
        ratio (short input, long output). A summarisation persona
        produces a low ratio. Personas tend to cluster.
        """
        if self.input_total == 0:
            return 0.0
        return self.output_tokens / self.input_total


@dataclass(frozen=True, slots=True)
class TimingSnapshot:
    """Per-turn timing decomposition (ns) sourced from core.timing.

    Mirrors :class:`core.timing.TimingRecord`'s duration properties but
    flattened into a struct so the ring buffer can hold it directly without
    a back-reference to the timing module.
    """

    build_request_ns: int | None
    network_out_ns: int | None
    prefill_ns: int | None
    decode_ns: int | None
    network_back_ns: int | None
    total_ns: int

    @property
    def ttft_ns(self) -> int | None:
        """Time to first token: build + send + prefill (none if any are missing)."""
        if (
            self.build_request_ns is None
            or self.network_out_ns is None
            or self.prefill_ns is None
        ):
            return None
        return self.build_request_ns + self.network_out_ns + self.prefill_ns


@dataclass(frozen=True, slots=True)
class TurnRecord:
    """One complete chat turn captured for the metrics tab.

    Combines the token flow snapshot, the timing snapshot, and a turn
    identifier so the ring buffer can present a coherent per-turn row to
    the dashboard.
    """

    request_id: str
    turn_index: int  # monotonic counter from the ring buffer
    timestamp_ns: int  # epoch nanoseconds when the turn completed
    flow: TokenFlowSnapshot
    timing: TimingSnapshot

    @property
    def total_ns(self) -> int:
        """Convenience accessor: end-to-end wall time for this turn."""
        return self.timing.total_ns


@dataclass(frozen=True, slots=True)
class GuapoIndirectStats:
    """What we can learn about guapo from outside the frozen interface.

    Populated by :class:`core.observability.guapo_provider.IndirectProvider`
    via background polling of ``/healthz``, ``/v1/models``, and the most
    recent real chat call's TTFT/decode rate.

    The hardware stats (GPU util, watts, temp, mem) are deliberately
    ``None`` here — guapo's frozen surface doesn't expose them, and the
    user has decided not to patch a ``/v1/stats`` endpoint at this time.
    The :class:`core.observability.guapo_provider.DirectProvider` stub is
    ready for the day those become available without any reshape upstream.
    """

    healthy: bool
    whisper_loaded: bool
    tts_loaded: bool
    health_rtt_ms_60s_avg: float | None
    health_rtt_ms_60s_stddev: float | None  # the chat-queue-signal load proxy
    last_chat_ttft_ms: float | None
    last_chat_decode_tok_per_sec: float | None
    models_available: int


@dataclass(frozen=True, slots=True)
class SlimHostStats:
    """Sanitised host stats for slim, mirroring the sidecar allowlist.

    Populated by :class:`core.observability.slim_stats.SlimStatsClient`
    polling the host-stats sidecar container's internal HTTP endpoint.

    Explicitly excludes anything that could fingerprint the host:
    process list, PIDs, usernames, hostname, IPs, MAC addresses, mount
    points, network interface names, kernel/OS/CPU-model strings.
    """

    cpu_utilization_pct: float
    cpu_load_1m: float
    cpu_load_5m: float
    cpu_load_15m: float
    cpu_count: int
    mem_used_mb: int
    mem_total_mb: int
    disk_used_gb: float
    disk_total_gb: float
    net_rx_bytes_per_sec: int
    net_tx_bytes_per_sec: int
    uptime_sec: int


# ────────────────────────────────────────────────────────────────────────────
# Constants used by callers when they need to know record-level limits
# ────────────────────────────────────────────────────────────────────────────

DEFAULT_RING_BUFFER_SIZE: Final[int] = 500
"""How many TurnRecord rows to keep in memory by default."""
