"""Locked observability and chat infrastructure for the wize73 class chatbot.

This package is CODEOWNERS-protected. Students consume the public APIs but
cannot edit any module under here. The locked surface guarantees that the
measurement numbers in `/metrics` stay trustworthy across PRs and that the
security preamble + output filter cannot be bypassed by student code.

Public sub-packages:

* :mod:`core.chat` — OpenAI client wrapper, ``build_request`` slots,
  security preamble, output filter.
* :mod:`core.observability` — the ``/metrics`` sub-app, ring buffer,
  projection calculator, dashboards.
* :mod:`core.ops` — the instructor-only ``/ops`` dashboard.
* :mod:`core.timing` — per-request ``t0..t5`` instrumentation.
* :mod:`core.agents` — agent prompts, rules, and runners for the 9 PR agents.
* :mod:`core.prompts` — baseline locked system prompt.
"""
