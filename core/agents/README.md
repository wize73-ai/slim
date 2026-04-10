# `core/agents/` — prompts, rules, and runners for the 9 PR agents

Locked. Students **read** these files to learn what the agents look at, but
cannot edit them.

## What lives here

- `red_team_probes.yaml` — 12 pre-written adversarial probes (jailbreaks, prompt
  injection, role escapes, system-prompt-leak attempts).
- `blue_team_checklist.yaml` — defensive review rubric (error handling, input
  validation, fallback paths for guapo 5xx).
- `classroom_safety_rules.yaml` — tunable strictness rules for content review.
- `malicious_patterns.yaml` — semgrep custom rules for agent 9.
- `malicious_review_prompts.md` — dual-judge templates for agent 9.
- `secrets_review_prompt.md` — obfuscation-property check for agent 1.
- `slop_scope_prompt.md` — scope-vs-intent judge for agent 8.
- `pythonic_review_prompt.md` — code-quality LLM sub-step for agent 2.
- `judge_rubrics.yaml` — shared structured-output templates with nonce-delimited
  input and fail-closed `VERDICT: PASS|FAIL` parsing.
- `lint_explanations.yaml` — educational "why this matters" messages surfaced on
  every lint failure (agent 2).
- `discipline_explanations.yaml` — same for agent 6 hygiene failures.
- `runners/` — the Python scripts each workflow invokes. They do the static
  analysis locally and make narrow LLM calls through the agent-inference proxy
  on slim (which is the only thing that talks to guapo).

## Why students can read these

The agents are part of the curriculum. When agent 3 posts "your persona leaked
the system prompt on probe 7/12," the student can open `red_team_probes.yaml`
and see exactly what probe 7 was. That's the teaching moment — learning to
think like the red team requires seeing the red team's playbook.

## Why students can't edit these

For the same reason `core/` is locked in general: if students could tune the
rules, the gate becomes meaningless. You can't grade a test the student got
to write.

## LLM calls

All LLM calls go through the agent-inference proxy on slim at
`https://class.wize73.com/agents-llm` with a bearer token (a GitHub Actions
secret). The proxy forwards to guapo's phi-4-mini via Tailscale, rate-limits
per-PR, caches by input hash, and can be killed instantly from the instructor
ops dashboard if guapo starts starving live student traffic.

No agent ever makes a network call to anywhere else. No Anthropic API, no
external services. Everything is on the frozen surface.
