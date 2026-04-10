"""Tests for core.chat — focuses on the security boundary.

These tests cover the OUTPUT FILTER and SECURITY PREAMBLE, both of which
are load-bearing safety mechanisms. If any of these fail, the obfuscation
property is broken and guapo's URL / IPs / model IDs could leak to students
through the chatbot output.

The build_request and LabelledMessages tests verify the labelled-slot
contract that the metrics tab depends on.
"""

from __future__ import annotations

import pytest

from core.chat.security import (
    SECURITY_PREAMBLE,
    StreamFilter,
    compose_system_prompt,
)


# ────────────────────────────────────────────────────────────────────────────
# StreamFilter — the output redaction filter
# ────────────────────────────────────────────────────────────────────────────


class TestStreamFilterRedaction:
    """Verify the filter catches every known guapo identifier."""

    @pytest.mark.parametrize(
        "leak",
        [
            "phi-4-mini",
            "/models/phi-4-mini",
            "100.91.130.128",
            "192.168.1.103",
            "guapo",
            "Guapo",
            "GUAPO",
            "xtts_v2",
            "xtts-v2",
            "large-v3-turbo",
            "tts_models/multilingual/multi-dataset/xtts_v2",
        ],
    )
    def test_redacts_known_leak(self, leak):
        f = StreamFilter()
        result = f.feed(f"my model is {leak} and that's a fact") + f.flush()
        assert leak.lower() not in result.lower(), (
            f"leak {leak!r} reached output: {result!r}"
        )
        assert f.redaction_count >= 1

    def test_no_redaction_on_clean_text(self):
        f = StreamFilter()
        clean = "The capital of France is Paris. Two plus two is four."
        result = f.feed(clean) + f.flush()
        assert result == clean
        assert f.redaction_count == 0

    def test_catches_pattern_split_across_chunks(self):
        f = StreamFilter()
        result = f.feed("the model is phi-4-")
        result += f.feed("mini, and that's all")
        result += f.flush()
        assert "phi-4-mini" not in result
        assert f.redaction_count == 1

    def test_catches_long_pattern_across_three_chunks(self):
        f = StreamFilter()
        result = f.feed("the path is tts_models/")
        result += f.feed("multilingual/multi-")
        result += f.feed("dataset/xtts_v2 here")
        result += f.flush()
        assert "tts_models/multilingual/multi-dataset/xtts_v2" not in result
        assert f.redaction_count >= 1

    def test_redaction_count_accumulates_across_calls(self):
        f = StreamFilter()
        f.feed("phi-4-mini and 100.91.130.128 and guapo")
        f.flush()
        assert f.redaction_count == 3

    def test_redacts_inside_url(self):
        f = StreamFilter()
        result = f.feed("see http://100.91.130.128:8000/v1/models for details")
        result += f.flush()
        assert "100.91.130.128" not in result

    def test_word_boundary_for_guapo(self):
        f = StreamFilter()
        result = f.feed("guacamole is delicious")
        result += f.flush()
        assert "guacamole" in result
        assert f.redaction_count == 0

    def test_handles_empty_chunks(self):
        f = StreamFilter()
        f.feed("")
        f.feed("")
        out = f.flush()
        assert out == ""
        assert f.redaction_count == 0

    def test_flush_can_be_called_multiple_times(self):
        f = StreamFilter()
        f.feed("hello")
        first = f.flush()
        second = f.flush()
        assert first == "hello"
        assert second == ""


# ────────────────────────────────────────────────────────────────────────────
# Security preamble composition
# ────────────────────────────────────────────────────────────────────────────


class TestSecurityPreamble:
    """Verify the security preamble is correctly composed and present in output."""

    def test_preamble_always_first(self):
        result = compose_system_prompt(
            baseline="You are a helpful assistant.",
            student_system="Be terse.",
            persona="You like cats.",
        )
        assert result.startswith(SECURITY_PREAMBLE.strip())

    def test_preamble_has_security_directives(self):
        assert "URL" in SECURITY_PREAMBLE
        assert "IP address" in SECURITY_PREAMBLE
        assert "model" in SECURITY_PREAMBLE.lower()
        assert "hostname" in SECURITY_PREAMBLE.lower()

    def test_optional_layers(self):
        result = compose_system_prompt(baseline="hi")
        assert SECURITY_PREAMBLE.strip() in result
        assert "hi" in result

    def test_layers_in_order(self):
        result = compose_system_prompt(
            baseline="BASELINE",
            student_system="STUDENT",
            persona="PERSONA",
        )
        idx_preamble = result.index(SECURITY_PREAMBLE.strip())
        idx_baseline = result.index("BASELINE")
        idx_student = result.index("STUDENT")
        idx_persona = result.index("PERSONA")
        assert idx_preamble < idx_baseline < idx_student < idx_persona

    def test_empty_optional_layers_omitted(self):
        result = compose_system_prompt(
            baseline="BASELINE",
            student_system="",
            persona="",
        )
        # Should not have trailing empty lines from concatenating empty parts
        assert result.endswith("BASELINE")


# ────────────────────────────────────────────────────────────────────────────
# build_request — labelled message construction
# Skipped if tiktoken is not available in the test environment.
# ────────────────────────────────────────────────────────────────────────────

tiktoken = pytest.importorskip("tiktoken")


class TestBuildRequest:
    """Verify build_request produces correctly labelled messages."""

    def test_minimal_request(self):
        from core.chat.messages import build_request

        msgs = build_request(baseline="You are a helpful assistant.", user="Hello")
        assert msgs.user_text == "Hello"
        assert msgs.user_tokens > 0
        assert msgs.system_tokens > 0
        assert msgs.persona_tokens == 0
        assert msgs.examples_tokens == 0
        assert msgs.history_tokens == 0

    def test_full_request(self):
        from core.chat.messages import FewShotExample, HistoryMessage, build_request

        msgs = build_request(
            baseline="Baseline.",
            student_system="Student.",
            persona="Persona.",
            examples=(FewShotExample(user="q1", assistant="a1"),),
            history=(HistoryMessage(role="user", content="prior"),),
            user="now",
        )
        assert msgs.persona_tokens > 0
        assert msgs.examples_tokens > 0
        assert msgs.history_tokens > 0
        assert msgs.total_input_tokens > 0

    def test_to_openai_messages_format(self):
        from core.chat.messages import FewShotExample, build_request

        msgs = build_request(
            baseline="be helpful",
            examples=(FewShotExample(user="q", assistant="a"),),
            user="hello",
        )
        flat = msgs.to_openai_messages()
        assert flat[0]["role"] == "system"
        assert flat[1]["role"] == "user"
        assert flat[1]["content"] == "q"
        assert flat[2]["role"] == "assistant"
        assert flat[2]["content"] == "a"
        assert flat[-1]["role"] == "user"
        assert flat[-1]["content"] == "hello"

    def test_total_input_tokens_sums_correctly(self):
        from core.chat.messages import FewShotExample, HistoryMessage, build_request

        msgs = build_request(
            baseline="x",
            persona="y",
            examples=(FewShotExample(user="a", assistant="b"),),
            history=(HistoryMessage(role="user", content="c"),),
            user="d",
        )
        expected = (
            msgs.system_tokens
            + msgs.examples_tokens
            + msgs.history_tokens
            + msgs.user_tokens
        )
        assert msgs.total_input_tokens == expected

    def test_persona_tokens_reported_independently(self):
        from core.chat.messages import build_request

        with_persona = build_request(
            baseline="x", persona="some persona text", user="hi"
        )
        without_persona = build_request(baseline="x", user="hi")
        # Persona text contributes to system_tokens (it's embedded there)
        assert with_persona.system_tokens > without_persona.system_tokens
        # And is also reported separately
        assert with_persona.persona_tokens > 0
        assert without_persona.persona_tokens == 0

    def test_labelled_messages_immutable(self):
        from core.chat.messages import build_request

        msgs = build_request(baseline="b", user="u")
        with pytest.raises((AttributeError, TypeError)):
            msgs.user_text = "hacked"  # type: ignore[misc]
