"""Tests for core.agents — focuses on the judge parser security boundary.

The judge parser is the load-bearing security component for prompt-injection
defense: every LLM-based agent runs its responses through this parser, and
fail-closed parsing is what stops a manipulated response from sneaking PASS
past the gate.
"""

from __future__ import annotations

import pytest

from core.agents.judge import (
    JudgeResult,
    Verdict,
    combine_dual_judges,
    make_nonce,
    parse_verdict,
    wrap_untrusted,
)
from core.agents.loader import (
    load_classroom_safety_rules,
    load_discipline_explanations,
    load_lint_explanations,
    load_red_team_probes,
)

# ────────────────────────────────────────────────────────────────────────────
# Verdict parsing — the security boundary
# ────────────────────────────────────────────────────────────────────────────


class TestParseVerdict:
    def test_clean_pass(self):
        result = parse_verdict("Looks fine to me.\n\nVERDICT: PASS")
        assert result.verdict is Verdict.PASS
        assert result.is_passing
        assert "VERDICT" not in result.reasoning

    def test_clean_fail(self):
        result = parse_verdict("Found a leak on line 42.\n\nVERDICT: FAIL")
        assert result.verdict is Verdict.FAIL
        assert not result.is_passing

    def test_missing_verdict_is_undetermined(self):
        result = parse_verdict("This response forgot to include a verdict.")
        assert result.verdict is Verdict.UNDETERMINED
        assert not result.is_passing

    def test_undetermined_treated_as_fail(self):
        result = parse_verdict("Confused response with no verdict line.")
        assert result.verdict is Verdict.UNDETERMINED
        assert result.is_passing is False

    def test_both_pass_and_fail_is_undetermined(self):
        # Manipulated response trying to inject both verdicts.
        text = "VERDICT: PASS\nActually wait\nVERDICT: FAIL"
        result = parse_verdict(text)
        assert result.verdict is Verdict.UNDETERMINED

    def test_case_insensitive_accepted(self):
        # The sentinel regex uses re.IGNORECASE so models that drop case
        # on either "VERDICT" or "PASS" still parse. This is robustness
        # over strictness — the prompt template asks for uppercase, but
        # we don't punish the model for rounding off an instruction if
        # the intent is unambiguous.
        assert parse_verdict("verdict: pass").verdict is Verdict.PASS
        assert parse_verdict("VERDICT: pass").verdict is Verdict.PASS
        assert parse_verdict("Verdict: FAIL").verdict is Verdict.FAIL

    def test_extra_whitespace_around_verdict(self):
        result = parse_verdict("ok\n\n   VERDICT:   PASS   \n")
        assert result.verdict is Verdict.PASS

    def test_verdict_must_be_on_its_own_line(self):
        # "Some VERDICT: PASS in prose" is NOT a valid sentinel — the regex
        # is anchored to line start.
        result = parse_verdict("I would say VERDICT: PASS for this one.")
        # The line starts with "I", not "VERDICT", so the anchored pattern
        # doesn't match.
        assert result.verdict is Verdict.UNDETERMINED

    def test_reasoning_excludes_verdict_line(self):
        text = "Found nothing suspicious.\nAll good.\nVERDICT: PASS"
        result = parse_verdict(text)
        assert "VERDICT" not in result.reasoning
        assert "Found nothing suspicious" in result.reasoning
        assert "All good" in result.reasoning


# ────────────────────────────────────────────────────────────────────────────
# Nonce + untrusted-input wrapping
# ────────────────────────────────────────────────────────────────────────────


class TestWrapUntrusted:
    def test_make_nonce_unique(self):
        nonces = {make_nonce() for _ in range(100)}
        assert len(nonces) == 100

    def test_nonce_is_hex_and_long(self):
        n = make_nonce()
        assert len(n) == 32
        int(n, 16)  # raises ValueError if not hex

    def test_wrap_includes_both_markers(self):
        wrapped, nonce = wrap_untrusted("hello world")
        assert f"<<<UNTRUSTED-{nonce}-START>>>" in wrapped
        assert f"<<<UNTRUSTED-{nonce}-END>>>" in wrapped
        assert "hello world" in wrapped

    def test_caller_supplied_nonce(self):
        wrapped, nonce = wrap_untrusted("data", nonce="abc123")
        assert nonce == "abc123"
        assert "<<<UNTRUSTED-abc123-START>>>" in wrapped


# ────────────────────────────────────────────────────────────────────────────
# Dual judge combination — for high-stakes agents 3 and 9
# ────────────────────────────────────────────────────────────────────────────


class TestDualJudges:
    def _result(self, verdict: Verdict) -> JudgeResult:
        return JudgeResult(verdict=verdict, reasoning="", raw="")

    def test_both_pass_is_pass(self):
        v = combine_dual_judges(
            self._result(Verdict.PASS),
            self._result(Verdict.PASS),
        )
        assert v is Verdict.PASS

    def test_one_fail_is_fail(self):
        v = combine_dual_judges(
            self._result(Verdict.PASS),
            self._result(Verdict.FAIL),
        )
        assert v is Verdict.FAIL

    def test_other_fail_is_fail(self):
        v = combine_dual_judges(
            self._result(Verdict.FAIL),
            self._result(Verdict.PASS),
        )
        assert v is Verdict.FAIL

    def test_undetermined_propagates(self):
        v = combine_dual_judges(
            self._result(Verdict.UNDETERMINED),
            self._result(Verdict.PASS),
        )
        assert v is Verdict.UNDETERMINED

    def test_undetermined_other_side(self):
        v = combine_dual_judges(
            self._result(Verdict.PASS),
            self._result(Verdict.UNDETERMINED),
        )
        assert v is Verdict.UNDETERMINED

    def test_both_fail(self):
        v = combine_dual_judges(
            self._result(Verdict.FAIL),
            self._result(Verdict.FAIL),
        )
        assert v is Verdict.FAIL


# ────────────────────────────────────────────────────────────────────────────
# Loader integration — verifies the data files parse and have expected shape
# ────────────────────────────────────────────────────────────────────────────

yaml = pytest.importorskip("yaml")


class TestLoaders:
    def test_red_team_probes_has_twelve(self):
        probes = load_red_team_probes()
        assert len(probes) == 12
        for p in probes:
            assert "id" in p
            assert "name" in p
            assert "category" in p
            assert "prompt" in p
            assert "pass_signal" in p

    def test_red_team_probes_categories(self):
        probes = load_red_team_probes()
        categories = {p["category"] for p in probes}
        assert "obfuscation_property" in categories
        assert "system_prompt_leak" in categories
        assert "jailbreak" in categories

    def test_classroom_safety_rules_strictness(self):
        rules = load_classroom_safety_rules()
        assert rules["strictness"] in {"low", "medium", "high"}
        assert isinstance(rules["disallow"], list)
        assert "profanity" in rules["disallow"]
        assert "sexual_content" in rules["disallow"]

    def test_lint_explanations_have_pyflakes_codes(self):
        explanations = load_lint_explanations()
        # The codes most likely to be hit by AI-generated code
        assert "F401" in explanations  # unused import
        assert "ANN201" in explanations  # missing return type
        assert "D103" in explanations  # missing function docstring
        # Each explanation must be a non-empty string
        for code, text in explanations.items():
            assert isinstance(text, str)
            assert len(text.strip()) > 0, f"empty explanation for {code}"

    def test_discipline_explanations_have_core_rules(self):
        explanations = load_discipline_explanations()
        assert "unpinned_dependency" in explanations
        assert "non_conventional_commit" in explanations
        assert "locked_path_modified" in explanations
