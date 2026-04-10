# `core/agents/runners/` — agent runner scripts

Locked. One Python script per agent. Each is invoked by its matching
workflow in `.github/workflows/pr-NN-*.yml`.

Runners follow a common shape:

1. Load the diff from the PR.
2. Run deterministic static checks first (semgrep, bandit, ruff, AST walks,
   regex, custom detectors).
3. If the static layer is inconclusive, make **narrow** LLM calls to the
   agent-inference proxy on slim with nonce-delimited untrusted input and
   strict `VERDICT: PASS|FAIL` output templates.
4. Parse with fail-closed semantics: ambiguous output → FAIL.
5. Emit a GitHub check run conclusion plus a PR comment with educational
   explanation pulled from `core/agents/lint_explanations.yaml` or similar.

See the parent `README.md` for the list of agents and what each one does.
