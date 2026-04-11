"""Agent prompts, rules, and Python helpers for the 9 PR agents.

This package is the SHARED LIBRARY that the .github/workflows/pr-NN-*.yml
agents call into. The actual workflow files live in .github/workflows/
and are written in task #15; this commit ships the data + helpers they
will use.

Public surface:

* :func:`call_proxy` and friends — async client for the agent inference
  proxy on slim. The only network path between CI and guapo.
* :class:`Verdict`, :class:`JudgeResult`, :func:`parse_verdict`,
  :func:`make_nonce`, :func:`wrap_untrusted`, :func:`combine_dual_judges` —
  fail-closed parser + prompt-injection defense for free-text LLM
  responses (phi-4-mini has no tool-use mode).
* :func:`load_text`, :func:`load_yaml`, plus typed loaders for each
  prompt/rule file under ``core/agents/prompts/``.

Students can READ everything under this package — including the prompts
and rules — and learn what the agents look at. They cannot edit it
because the entire ``core/`` package is CODEOWNERS-protected.
"""

from core.agents.judge import (
    JudgeResult,
    Verdict,
    combine_dual_judges,
    make_nonce,
    parse_verdict,
    wrap_untrusted,
)
from core.agents.loader import (
    PROMPTS_DIR,
    load_classroom_safety_rules,
    load_discipline_explanations,
    load_judge_templates,
    load_lint_explanations,
    load_red_team_probes,
    load_text,
    load_yaml,
)
from core.agents.proxy import (
    AgentProxyAuthFailed,
    AgentProxyError,
    AgentProxyRateLimited,
    AgentProxyUnavailable,
    ProxyResponse,
    call_proxy,
)

__all__ = [
    "AgentProxyAuthFailed",
    "AgentProxyError",
    "AgentProxyRateLimited",
    "AgentProxyUnavailable",
    "JudgeResult",
    "PROMPTS_DIR",
    "ProxyResponse",
    "Verdict",
    "call_proxy",
    "combine_dual_judges",
    "load_classroom_safety_rules",
    "load_discipline_explanations",
    "load_judge_templates",
    "load_lint_explanations",
    "load_red_team_probes",
    "load_text",
    "load_yaml",
    "make_nonce",
    "parse_verdict",
    "wrap_untrusted",
]
