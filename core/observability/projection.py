"""Projection calculator with rolling-window coefficients.

The killer pedagogical tool: students enter a planned architecture
(system size, persona size, few-shot count, history retention, average
message lengths, planned turn count) and see projected per-turn token
costs, processing times, and FLOPs curves *before* they actually run
anything. The bidirectional framing extends to projection — outputs
include both prefill and decode time/flops separately.

Coefficients (avg tok/s, tokenizer ratios, FLOPs constants) refresh from
a rolling window of real measurements as students use the system. The
projection improves over the class session as the buffer fills.

Compare-to-actual is one of the key buttons in the metrics tab UI: paste
your projection alongside the curve you actually produced and look for
the gap. The gap is the lesson.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Final, Iterable

from core.observability.records import TurnRecord

# ────────────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────────────

# Phi-4-mini parameter count for the FLOPs estimate. Sourced from Microsoft's
# release notes — it's an MoE-style model nominally ~3.8B active parameters.
# The constant 2 in the formula is the standard transformer inference
# multiplier (2 FLOPs per parameter per token, one for the matmul, one for
# the accumulate).
PHI_4_MINI_PARAMETERS: Final[int] = 3_800_000_000

# Default tok/sec used when the rolling window is empty (e.g. first turn).
# This is a deliberately conservative number; the calculator updates it
# from real measurements as soon as one turn completes.
DEFAULT_TOK_PER_SEC: Final[float] = 50.0

# Phi-4-mini context window. Used by projections to flag the turn at which
# the planned architecture would hit the wall.
PHI_4_MINI_CONTEXT_TOKENS: Final[int] = 8192

# Per-turn FLOPs estimate uses input + output token counts:
#   prefill_flops ≈ 2 × N_params × input_tokens
#   decode_flops  ≈ 2 × N_params × output_tokens
#
# This is the standard back-of-envelope inference FLOPs formula and matches
# what students will see in any modern LLM compute paper.


# ────────────────────────────────────────────────────────────────────────────
# Input shape: an architecture spec
# ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ArchitectureSpec:
    """A planned chatbot configuration to project costs for.

    All sizes are in tokens. Use :func:`core.chat.count_tokens` to
    estimate token counts from real text before plugging them into a spec.
    """

    system_tokens: int
    persona_tokens: int
    few_shot_count: int
    avg_few_shot_tokens: int
    history_retention_turns: int
    avg_user_msg_tokens: int
    avg_assistant_reply_tokens: int
    planned_turns: int


# ────────────────────────────────────────────────────────────────────────────
# Output shape: per-turn projection rows
# ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ProjectedTurn:
    """One row of the projection: what turn N is expected to look like.

    Bidirectional fields (prefill vs decode, input vs output) so the
    projection chart shape mirrors the measurement chart shape and the
    "compare projection to actual" overlay reads cleanly.
    """

    turn_index: int
    input_tokens: int
    output_tokens: int
    context_fill_pct: float

    prefill_flops: int
    decode_flops: int

    prefill_seconds: float
    decode_seconds: float

    @property
    def total_tokens(self) -> int:
        """Sum of input + output for this turn."""
        return self.input_tokens + self.output_tokens

    @property
    def total_seconds(self) -> float:
        """Sum of prefill + decode time for this turn."""
        return self.prefill_seconds + self.decode_seconds


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    """The full projection: per-turn rows plus summary metrics.

    The first turn at which the planned architecture exceeds the model's
    context window is flagged in :attr:`context_wall_at_turn` so the UI
    can render the trajectory with a clear "you ran out of context here"
    marker.
    """

    spec: ArchitectureSpec
    turns: tuple[ProjectedTurn, ...]
    coefficients: ProjectionCoefficients
    context_wall_at_turn: int | None


# ────────────────────────────────────────────────────────────────────────────
# Coefficients fit from the rolling window of real measurements
# ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ProjectionCoefficients:
    """Empirically fit constants used by the projection.

    These refresh on every projection request from the rolling window of
    actual measurements in the ring buffer. When the window is empty
    (first turn of the class session), defaults are used.
    """

    decode_tok_per_sec: float
    prefill_seconds_per_token: float  # ns/token measured, converted
    sample_size: int  # how many turns went into the fit (0 means defaults)


def fit_coefficients(records: Iterable[TurnRecord]) -> ProjectionCoefficients:
    """Compute projection coefficients from a window of real turn records.

    Uses median (not mean) of per-turn rates to be robust against the cold-
    start outlier (first chat call after guapo restart can be 25 seconds for
    model load). Only considers turns where both prefill and decode timing
    are populated *and* output tokens > 0.

    Args:
        records: A windowed iterable of :class:`TurnRecord` rows.

    Returns:
        Coefficients suitable for plugging into :func:`project`.
    """
    decode_rates: list[float] = []
    prefill_per_token: list[float] = []
    for r in records:
        if r.timing.decode_ns is None or r.timing.prefill_ns is None:
            continue
        if r.flow.output_tokens <= 0 or r.flow.input_total <= 0:
            continue
        decode_seconds = r.timing.decode_ns / 1_000_000_000
        if decode_seconds > 0:
            decode_rates.append(r.flow.output_tokens / decode_seconds)
        prefill_seconds = r.timing.prefill_ns / 1_000_000_000
        prefill_per_token.append(prefill_seconds / r.flow.input_total)

    sample_size = min(len(decode_rates), len(prefill_per_token))
    if sample_size == 0:
        return ProjectionCoefficients(
            decode_tok_per_sec=DEFAULT_TOK_PER_SEC,
            prefill_seconds_per_token=1.0 / DEFAULT_TOK_PER_SEC,
            sample_size=0,
        )

    return ProjectionCoefficients(
        decode_tok_per_sec=statistics.median(decode_rates),
        prefill_seconds_per_token=statistics.median(prefill_per_token),
        sample_size=sample_size,
    )


# ────────────────────────────────────────────────────────────────────────────
# The projection itself
# ────────────────────────────────────────────────────────────────────────────


def project(
    spec: ArchitectureSpec,
    coefficients: ProjectionCoefficients,
    *,
    context_window: int = PHI_4_MINI_CONTEXT_TOKENS,
    parameters: int = PHI_4_MINI_PARAMETERS,
) -> ProjectionResult:
    """Project per-turn token, FLOPs, and time curves for an architecture.

    History grows linearly: at turn N the history contains the (N-1) prior
    user messages and (N-1) prior assistant replies, capped at
    ``spec.history_retention_turns`` turns.

    The fixed cost per turn (system + persona + few-shots) is paid every
    turn forever — that's the lesson the chart visualises.

    Args:
        spec: The planned architecture to project.
        coefficients: Empirically fit constants from the rolling window.
        context_window: Token limit at which to flag the context wall.
            Defaults to phi-4-mini's 8192.
        parameters: Active parameter count for the FLOPs estimate.
            Defaults to phi-4-mini's 3.8B.

    Returns:
        A :class:`ProjectionResult` with one :class:`ProjectedTurn` per
        planned turn plus the context-wall flag.
    """
    fixed_input = (
        spec.system_tokens
        + spec.persona_tokens
        + spec.few_shot_count * spec.avg_few_shot_tokens
    )

    rows: list[ProjectedTurn] = []
    context_wall: int | None = None

    for turn_index in range(1, spec.planned_turns + 1):
        history_turns_in_window = min(turn_index - 1, spec.history_retention_turns)
        history_tokens = history_turns_in_window * (
            spec.avg_user_msg_tokens + spec.avg_assistant_reply_tokens
        )
        input_tokens = fixed_input + history_tokens + spec.avg_user_msg_tokens
        output_tokens = spec.avg_assistant_reply_tokens

        prefill_flops = 2 * parameters * input_tokens
        decode_flops = 2 * parameters * output_tokens

        prefill_seconds = input_tokens * coefficients.prefill_seconds_per_token
        decode_seconds = (
            output_tokens / coefficients.decode_tok_per_sec
            if coefficients.decode_tok_per_sec > 0
            else 0.0
        )

        context_fill_pct = 100.0 * (input_tokens + output_tokens) / context_window

        rows.append(
            ProjectedTurn(
                turn_index=turn_index,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                context_fill_pct=context_fill_pct,
                prefill_flops=prefill_flops,
                decode_flops=decode_flops,
                prefill_seconds=prefill_seconds,
                decode_seconds=decode_seconds,
            )
        )

        if context_wall is None and (input_tokens + output_tokens) > context_window:
            context_wall = turn_index

    return ProjectionResult(
        spec=spec,
        turns=tuple(rows),
        coefficients=coefficients,
        context_wall_at_turn=context_wall,
    )
