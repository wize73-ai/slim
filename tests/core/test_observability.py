"""Tests for core.observability — focuses on the ring buffer + projection.

These are the parts that don't need a network or FastAPI to exercise.
The provider tests live elsewhere because they require httpx + a fake
HTTP server.
"""

from __future__ import annotations

import time

import pytest

from core.observability.projection import (
    DEFAULT_TOK_PER_SEC,
    ArchitectureSpec,
    ProjectionCoefficients,
    fit_coefficients,
    project,
)
from core.observability.records import TimingSnapshot, TokenFlowSnapshot, TurnRecord
from core.observability.ring_buffer import (
    RingBuffer,
    aggregate_input_categories,
)
from core.timing import TimingRecord


# ────────────────────────────────────────────────────────────────────────────
# RingBuffer
# ────────────────────────────────────────────────────────────────────────────


class TestRingBuffer:
    def test_starts_empty(self):
        buf = RingBuffer(capacity=10)
        assert len(buf) == 0
        assert buf.latest() is None
        assert buf.snapshot() == ()

    def test_accepts_timing_pair_with_flow(self):
        buf = RingBuffer(capacity=10)
        flow = TokenFlowSnapshot(
            system_tokens=100,
            persona_tokens=20,
            examples_tokens=50,
            history_tokens=200,
            user_tokens=10,
            output_tokens=80,
        )
        buf.submit_flow("req-1", flow)
        rec = TimingRecord(
            request_id="req-1",
            t0_handler_enter_ns=0,
            t1_build_request_done_ns=1_000,
            t2_first_byte_out_ns=2_000,
            t3_first_sse_chunk_in_ns=3_000,
            t4_last_sse_chunk_in_ns=4_000,
            t5_handler_exit_ns=5_000,
        )
        buf.accept_timing_record(rec)
        assert len(buf) == 1
        latest = buf.latest()
        assert latest is not None
        assert latest.request_id == "req-1"
        assert latest.flow.system_tokens == 100
        assert latest.flow.output_tokens == 80
        assert latest.timing.total_ns == 5_000

    def test_accepts_timing_without_flow_uses_zero(self):
        buf = RingBuffer(capacity=10)
        rec = TimingRecord(
            request_id="orphan",
            t0_handler_enter_ns=0,
            t1_build_request_done_ns=None,
            t2_first_byte_out_ns=None,
            t3_first_sse_chunk_in_ns=None,
            t4_last_sse_chunk_in_ns=None,
            t5_handler_exit_ns=100,
        )
        buf.accept_timing_record(rec)
        latest = buf.latest()
        assert latest is not None
        assert latest.flow.system_tokens == 0
        assert latest.flow.output_tokens == 0

    def test_capacity_evicts_oldest(self):
        buf = RingBuffer(capacity=3)
        for i in range(5):
            buf.accept_timing_record(
                TimingRecord(
                    request_id=f"req-{i}",
                    t0_handler_enter_ns=0,
                    t1_build_request_done_ns=None,
                    t2_first_byte_out_ns=None,
                    t3_first_sse_chunk_in_ns=None,
                    t4_last_sse_chunk_in_ns=None,
                    t5_handler_exit_ns=100,
                )
            )
        snap = buf.snapshot()
        assert len(snap) == 3
        # The two oldest were evicted
        assert snap[0].request_id == "req-2"
        assert snap[-1].request_id == "req-4"

    def test_turn_index_monotonic(self):
        buf = RingBuffer(capacity=10)
        for i in range(3):
            buf.accept_timing_record(
                TimingRecord(
                    request_id=f"req-{i}",
                    t0_handler_enter_ns=0,
                    t1_build_request_done_ns=None,
                    t2_first_byte_out_ns=None,
                    t3_first_sse_chunk_in_ns=None,
                    t4_last_sse_chunk_in_ns=None,
                    t5_handler_exit_ns=100,
                )
            )
        snap = buf.snapshot()
        assert [r.turn_index for r in snap] == [0, 1, 2]

    def test_recent_returns_tail(self):
        buf = RingBuffer(capacity=10)
        for i in range(5):
            buf.accept_timing_record(
                TimingRecord(
                    request_id=f"req-{i}",
                    t0_handler_enter_ns=0,
                    t1_build_request_done_ns=None,
                    t2_first_byte_out_ns=None,
                    t3_first_sse_chunk_in_ns=None,
                    t4_last_sse_chunk_in_ns=None,
                    t5_handler_exit_ns=100,
                )
            )
        last_two = buf.recent(2)
        assert len(last_two) == 2
        assert last_two[0].request_id == "req-3"
        assert last_two[1].request_id == "req-4"

    def test_clear(self):
        buf = RingBuffer(capacity=10)
        buf.accept_timing_record(
            TimingRecord(
                request_id="x",
                t0_handler_enter_ns=0,
                t1_build_request_done_ns=None,
                t2_first_byte_out_ns=None,
                t3_first_sse_chunk_in_ns=None,
                t4_last_sse_chunk_in_ns=None,
                t5_handler_exit_ns=100,
            )
        )
        assert len(buf) == 1
        buf.clear()
        assert len(buf) == 0
        assert buf.latest() is None


# ────────────────────────────────────────────────────────────────────────────
# TokenFlowSnapshot computed properties
# ────────────────────────────────────────────────────────────────────────────


class TestTokenFlowSnapshot:
    def test_input_total_excludes_persona(self):
        flow = TokenFlowSnapshot(
            system_tokens=100,
            persona_tokens=30,  # already in system_tokens
            examples_tokens=50,
            history_tokens=200,
            user_tokens=10,
            output_tokens=80,
        )
        assert flow.input_total == 100 + 50 + 200 + 10  # persona NOT added

    def test_total_is_input_plus_output(self):
        flow = TokenFlowSnapshot(
            system_tokens=10,
            persona_tokens=0,
            examples_tokens=0,
            history_tokens=0,
            user_tokens=5,
            output_tokens=20,
        )
        assert flow.total == 10 + 5 + 20

    def test_asymmetry_above_one_is_expansive(self):
        flow = TokenFlowSnapshot(
            system_tokens=0,
            persona_tokens=0,
            examples_tokens=0,
            history_tokens=0,
            user_tokens=10,
            output_tokens=100,
        )
        assert flow.asymmetry == 10.0

    def test_asymmetry_below_one_is_compressive(self):
        flow = TokenFlowSnapshot(
            system_tokens=0,
            persona_tokens=0,
            examples_tokens=0,
            history_tokens=0,
            user_tokens=100,
            output_tokens=10,
        )
        assert flow.asymmetry == 0.1

    def test_asymmetry_zero_input_does_not_divide(self):
        flow = TokenFlowSnapshot(
            system_tokens=0,
            persona_tokens=0,
            examples_tokens=0,
            history_tokens=0,
            user_tokens=0,
            output_tokens=10,
        )
        assert flow.asymmetry == 0.0


# ────────────────────────────────────────────────────────────────────────────
# Projection
# ────────────────────────────────────────────────────────────────────────────


class TestProjection:
    def _spec(self, **overrides):
        defaults = {
            "system_tokens": 100,
            "persona_tokens": 50,
            "few_shot_count": 2,
            "avg_few_shot_tokens": 80,
            "history_retention_turns": 5,
            "avg_user_msg_tokens": 20,
            "avg_assistant_reply_tokens": 60,
            "planned_turns": 10,
        }
        defaults.update(overrides)
        return ArchitectureSpec(**defaults)

    def _default_coeffs(self):
        return ProjectionCoefficients(
            decode_tok_per_sec=50.0,
            prefill_seconds_per_token=0.001,
            sample_size=0,
        )

    def test_projection_returns_planned_turn_count(self):
        spec = self._spec(planned_turns=7)
        result = project(spec, self._default_coeffs())
        assert len(result.turns) == 7

    def test_history_grows_each_turn_until_cap(self):
        spec = self._spec(history_retention_turns=3, planned_turns=6)
        result = project(spec, self._default_coeffs())
        # Turn 1: history is 0 (no prior turns)
        # Turn 2: history is 1 turn (capped to 3)
        # Turn 3: history is 2 turns
        # Turn 4: history is 3 turns (cap)
        # Turn 5: still 3 (cap)
        # Turn 6: still 3 (cap)
        sizes = [t.input_tokens for t in result.turns]
        # Each turn after the first adds (avg_user + avg_reply) until cap
        # The increment is 80 (20+60), capped at 3 increments = 240
        increments = [sizes[i + 1] - sizes[i] for i in range(len(sizes) - 1)]
        # First three increments are 80, then increments stop
        assert increments[0] == 80
        assert increments[1] == 80
        assert increments[2] == 80
        assert increments[3] == 0
        assert increments[4] == 0

    def test_context_wall_flagged(self):
        # Tiny context window to force a wall
        spec = self._spec(planned_turns=5)
        result = project(
            spec,
            self._default_coeffs(),
            context_window=200,
        )
        assert result.context_wall_at_turn is not None
        # Context wall should be at the first turn that exceeds the window
        wall_turn = result.turns[result.context_wall_at_turn - 1]
        assert wall_turn.input_tokens + wall_turn.output_tokens > 200

    def test_no_context_wall_when_fits(self):
        spec = self._spec(planned_turns=3, system_tokens=10, persona_tokens=0,
                          few_shot_count=0, avg_user_msg_tokens=5,
                          avg_assistant_reply_tokens=5)
        result = project(spec, self._default_coeffs())
        assert result.context_wall_at_turn is None

    def test_flops_scale_with_tokens(self):
        spec = self._spec(planned_turns=2)
        result = project(spec, self._default_coeffs())
        # Turn 2 has more tokens than turn 1 (history grew), so more flops
        assert result.turns[1].prefill_flops > result.turns[0].prefill_flops
        # Decode flops are constant if output is constant
        assert result.turns[0].decode_flops == result.turns[1].decode_flops

    def test_decode_seconds_uses_coefficient(self):
        spec = self._spec(planned_turns=1, avg_assistant_reply_tokens=100)
        coeffs = ProjectionCoefficients(
            decode_tok_per_sec=10.0,
            prefill_seconds_per_token=0.001,
            sample_size=1,
        )
        result = project(spec, coeffs)
        # 100 tokens / 10 tok/s = 10 seconds
        assert result.turns[0].decode_seconds == pytest.approx(10.0)


# ────────────────────────────────────────────────────────────────────────────
# fit_coefficients
# ────────────────────────────────────────────────────────────────────────────


class TestFitCoefficients:
    def _make_record(
        self,
        *,
        request_id: str,
        prefill_ns: int | None,
        decode_ns: int | None,
        input_tokens: int,
        output_tokens: int,
    ) -> TurnRecord:
        flow = TokenFlowSnapshot(
            system_tokens=input_tokens,
            persona_tokens=0,
            examples_tokens=0,
            history_tokens=0,
            user_tokens=0,
            output_tokens=output_tokens,
        )
        timing = TimingSnapshot(
            build_request_ns=100,
            network_out_ns=100,
            prefill_ns=prefill_ns,
            decode_ns=decode_ns,
            network_back_ns=100,
            total_ns=10_000,
        )
        return TurnRecord(
            request_id=request_id,
            turn_index=0,
            timestamp_ns=time.time_ns(),
            flow=flow,
            timing=timing,
        )

    def test_empty_buffer_returns_defaults(self):
        coeffs = fit_coefficients([])
        assert coeffs.sample_size == 0
        assert coeffs.decode_tok_per_sec == DEFAULT_TOK_PER_SEC

    def test_skips_records_with_missing_timing(self):
        records = [
            self._make_record(
                request_id="a",
                prefill_ns=None,
                decode_ns=None,
                input_tokens=100,
                output_tokens=50,
            ),
        ]
        coeffs = fit_coefficients(records)
        assert coeffs.sample_size == 0

    def test_fits_from_real_records(self):
        records = [
            self._make_record(
                request_id=f"r-{i}",
                prefill_ns=200_000_000,  # 0.2s
                decode_ns=1_000_000_000,  # 1s
                input_tokens=200,
                output_tokens=50,
            )
            for i in range(5)
        ]
        coeffs = fit_coefficients(records)
        assert coeffs.sample_size == 5
        # 50 tokens / 1s = 50 tok/s
        assert coeffs.decode_tok_per_sec == pytest.approx(50.0)
        # 0.2s / 200 tokens = 0.001 s/token
        assert coeffs.prefill_seconds_per_token == pytest.approx(0.001)


# ────────────────────────────────────────────────────────────────────────────
# aggregate_input_categories
# ────────────────────────────────────────────────────────────────────────────


def test_aggregate_input_categories():
    records = [
        TurnRecord(
            request_id="r1",
            turn_index=0,
            timestamp_ns=0,
            flow=TokenFlowSnapshot(
                system_tokens=10,
                persona_tokens=5,
                examples_tokens=20,
                history_tokens=0,
                user_tokens=15,
                output_tokens=30,
            ),
            timing=TimingSnapshot(
                build_request_ns=None,
                network_out_ns=None,
                prefill_ns=None,
                decode_ns=None,
                network_back_ns=None,
                total_ns=100,
            ),
        ),
        TurnRecord(
            request_id="r2",
            turn_index=1,
            timestamp_ns=0,
            flow=TokenFlowSnapshot(
                system_tokens=10,
                persona_tokens=5,
                examples_tokens=20,
                history_tokens=45,
                user_tokens=20,
                output_tokens=40,
            ),
            timing=TimingSnapshot(
                build_request_ns=None,
                network_out_ns=None,
                prefill_ns=None,
                decode_ns=None,
                network_back_ns=None,
                total_ns=100,
            ),
        ),
    ]
    agg = aggregate_input_categories(records)
    assert agg["system"] == [10, 10]
    assert agg["history"] == [0, 45]
    assert agg["output"] == [30, 40]
