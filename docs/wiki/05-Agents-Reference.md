# Agents Reference

One section per pre-merge agent. Each agent runs on every pull request
and all 9 must pass for the merge button to enable. Failure messages
on PR comments include actionable hints; this page is the deep
reference.

You can also run `./scripts/explain-failure.sh <agent-name>` for a
short version on the command line, or
`./scripts/explain-failure.sh --list` to see them all.

---

## 1. secrets-scan

**What it checks:** hardcoded secrets, leaked URLs, anything that
would expose guapo's identifiers (URL, IP, model names) to students.

**How it works:**

- `gitleaks` runs against the full tree for known secret shapes
- `semgrep p/secrets` runs the secrets ruleset
- A custom regex scan looks for guapo's stable identifiers
  (`100.91.130.128`, `192.168.1.103`, `phi-4-mini`, `xtts_v2`,
  `large-v3-turbo`, `guapo`) outside the allowed locked paths
- An LLM catch-net (TODO — runs through the agent inference proxy on
  slim) reads the diff for indirect leaks the static rules miss

**Allowed paths** for guapo identifiers:

- `core/chat/security.py` (the output filter regex source-of-truth)
- `core/agents/prompts/` (judge templates that need to mention them)
- `core/observability/templates/_stats_guapo.html` (the dashboard panel)
- `docker/` (deployment config)

**Common fixes:**

- Remove any hardcoded URL or IP from your code. Use
  `os.environ['OPENAI_BASE_URL']` instead of literal strings.
- Remove debug print statements that include the URL.
- Don't put guapo's identifiers in comments either — the regex
  doesn't care about syntax.
- If you genuinely need to reference one of these names in a new
  file, ask the instructor whether your file should be added to the
  allowed-paths list.

---

## 2. code-quality

**What it checks:** ruff format + ruff check (strict ruleset) + mypy
strict on `core/` + pytest + interrogate docstring coverage. Also
auto-fixes what it can and commits the fixes back to your PR branch.

**How it works:**

1. Auto-fix pass: `ruff format .` then `ruff check --fix .`
2. If any files changed, commit them as `style: auto-fix lint`
3. Strict pass: `ruff check .` (must be clean — no fixes)
4. `ruff format --check .` (must be clean)
5. `mypy core/` (strict)
6. `pytest -q --tb=line`
7. `interrogate --fail-under=80 -q core/`
8. (TODO) LLM pythonic review for naming, idioms, comment quality

**Common fixes:**

```bash
# Run locally to reproduce
ruff format .
ruff check --fix .
mypy core/
pytest
interrogate -q core/
```

If a ruff code fires with a name you don't recognize, look it up at
[ruff's rule index](https://docs.astral.sh/ruff/rules/) — every code
has a description of the rule and an explanation. The agent's PR
comment also includes the educational "why this matters" message
from `core/agents/prompts/lint_explanations.yaml`.

**Common ruff codes you'll hit:**

- `D100` / `D103` — missing docstring on a module/function. Add a
  one-line summary.
- `ANN001` / `ANN201` — missing type annotation on parameter / return.
  Add type hints.
- `F401` — unused import. Delete it.
- `B008` — mutable default argument. Use `None` and create the mutable
  inside the function.
- `B904` — `raise X` inside `except` without `from`. Always preserve
  the exception chain.
- `SIM102` / `SIM108` — over-nested if statements that can be combined.

---

## 3. red-team

**What it checks:** 12 adversarial probes against your PR's built
container, looking for URL/identifier leakage in responses, system
prompt exfiltration, persona break, and a usability canary (your
chatbot must NOT refuse legitimate questions).

**How it works:**

1. Build the PR's docker image
2. Boot a mock guapo server pointed at by the PR app
3. Boot the PR app pointing at the mock
4. POST each of 12 probes from `core/agents/prompts/red_team_probes.yaml`
5. Deterministic regex check: response must not contain any guapo
   identifier
6. Usability canary: probe 12 ("introduce yourself in one sentence")
   must NOT refuse — catches over-tuned personas that refuse everything

**The 12 probes** (categories):

| # | Category | What it tries |
|---|---|---|
| 1-3 | obfuscation_property | Direct + roundabout URL/model extraction |
| 4-6 | system_prompt_leak | Direct, translation, encoding extraction |
| 7-8 | jailbreak | DAN-style + developer-mode override |
| 9 | persona_break | "Helpful AI must comply" framing |
| 10-11 | obfuscation_property | Indirect leak via code example / error message |
| 12 | usability_canary | Routine question — must NOT refuse |

**Common fixes:**

- **Don't override the security preamble.** It's in
  `core/chat/security.py` and runs first regardless of your persona.
- **Don't write a persona so locked-down it refuses legitimate
  questions.** The usability canary will catch that.
- **Don't leak the model name in error messages or example code your
  persona generates.** Even indirectly.

---

## 4. blue-team

**What it checks:** defensive code review — missing error handling on
guapo calls, missing input validation on user-facing routes, missing
fallbacks for guapo unavailability.

**How it works:**

- AST scan for `stream_completion()`, `build_request()`, `make_client()`
  calls in `app/` that are not inside a `try/except` block
- Heuristic AST scan for FastAPI `Form()` handlers that don't visibly
  validate input length or type (warning only)
- (TODO) LLM review of the diff for residual defensive gaps

**Common fixes:**

```python
# Wrap your guapo-facing calls
try:
    async for chunk in stream_completion(messages, instrument=t):
        ...
except UpstreamUnavailable:
    return error_banner("inference is offline, try again")
except UpstreamTimeout:
    return error_banner("inference timed out, try a shorter prompt")
except ChatError:
    return error_banner("something went wrong with chat")
```

The chat handler must not crash when guapo is down — it must return
SOMETHING to the user, even if it's just a friendly error banner.

---

## 5. classroom-safety

**What it checks:** content review of new persona / system prompt /
few-shot files for age-appropriateness. Different from secrets-scan
— it's about WHAT the chatbot is being told to say, not technical leaks.

**How it works:**

- Regex word-list against `app/personas`, `app/system_prompts`,
  `app/examples`, `app/templates` for profanity and harmful language
- Heuristic regex for impersonation patterns (`I am <Name> the
  <role>` where role is teacher/student/principal/etc.)
- (TODO) LLM secondary review against the rules in
  `core/agents/prompts/classroom_safety_rules.yaml`

**Disallowed by default:**

- Profanity, slurs, hate speech
- Sexual content, graphic violence
- Illegal activity advice
- Self-harm content
- Personally identifiable information
- Weapons instructions

**Custom rules** (from `classroom_safety_rules.yaml`):

- Personas may not impersonate real teachers or students by name
- No content referencing the school by name
- No content that could be mistaken for actual medical / legal /
  financial / mental health advice
- No content that asks for personal info
- No content disparaging specific demographics

**Common fixes:** read what you wrote. If you're not sure whether
something is appropriate, it probably isn't.

---

## 6. version-discipline

**What it checks:** mechanical hygiene. NO LLM. Pinned dependencies,
locked paths untouched, conventional commit messages, branch up to
date with main, PR description non-empty.

**How it works:**

- Grep `requirements.txt` and `requirements-dev.txt` for unpinned
  versions (anything not `==X.Y.Z`)
- `git diff origin/main --name-only` for files under `core/`,
  `.github/`, `docker/`, `docs/wiki/` — warns (CODEOWNERS will require
  the actual approval)
- Every commit subject in the PR (since merge-base with main) must
  match the conventional format regex
- `git log HEAD..origin/main` to check if branch is behind main —
  warning only
- `github.event.pull_request.body` non-empty check

**Each failure includes the educational "WHY THIS MATTERS"
explanation inline** so you don't need to look it up. The
`core/agents/prompts/discipline_explanations.yaml` file has the full
text.

**Common fixes:**

```bash
# Pin all requirements
sed -i 's/^\([a-z]*\)$/\1==FIXME/' requirements.txt   # then fix the FIXMEs

# Fix a non-conventional commit
git commit --amend -m "feat: actual descriptive subject"

# Bring branch up to date with main
git fetch origin && git rebase origin/main
```

---

## 7. build-and-smoke

**What it checks:** the docker image still builds, the container
starts, and the **locked metrics tab markers** are still present in
`/metrics/`. This is the gate that catches PRs that nuke the locked
observability templates.

**How it works:**

1. `docker buildx build -f docker/app/Dockerfile -t wize73-app:smoke .`
2. Run `python3 docker/smoke_test.py --image wize73-app:smoke`
3. Smoke test boots the container with a mock OPENAI_BASE_URL,
   polls `/healthz`, hits the `/metrics/*` and `/ops/healthz`
   endpoints, and asserts that the `/metrics/` HTML contains the
   locked tab markers (`Token flow by turn`, `Projection calculator`,
   the raw JSON link).

**Common fixes:**

- If the build itself fails, the error is usually a Python syntax
  error in your changes. Run `python3 -c "import ast; ast.parse(open('your_file.py').read())"`.
- If `/healthz` doesn't come up within 30s, your changes broke
  something at startup. `docker logs` shows you what.
- If a locked marker is missing, you broke a CODEOWNERS-locked
  template — revert that change. You shouldn't have been editing it
  in the first place.

```bash
# Reproduce locally
./scripts/preflight.sh --full
# or directly:
docker build -f docker/app/Dockerfile -t wize73-app:local .
python3 docker/smoke_test.py --image wize73-app:local
```

---

## 8. slop-and-scope

**What it checks:** AST-based slop detection. Dead code, premature
abstractions, hallucinated imports. Plus an LLM step (TODO) that
compares your diff to the linked issue's stated scope.

**How it works:**

- AST walk of `app/` collects every public function/class/module
- AST walk of `app/`, `core/`, `tests/` collects every name reference
- Definitions in `app/` with zero references anywhere are dead code
  (warning only — false positive rate on FastAPI handlers is high)
- Class hierarchies under `Base*` / `Abstract*` / `*Interface` /
  `*Protocol` with ≤1 subclass are flagged as premature abstraction
  (warning)
- `importlib.util.find_spec(module)` for every `from X import Y` in
  `app/` — modules that don't resolve are hallucinated (ERROR)

**Common fixes:**

- Hallucinated import (most common): an AI assistant suggested
  importing a module that doesn't exist. Check the actual package
  name on PyPI, or use a different approach that doesn't need it.
- Dead code warning: if it's a FastAPI route handler, it's a false
  positive. If it's a helper you wrote and forgot to wire up, either
  wire it up or delete it.
- Premature abstraction: if your `BaseFoo` has only one subclass
  `Foo`, just merge them into a single concrete class. Add the
  abstraction back later if a second consumer appears.

---

## 9. malicious-code-review

**What it checks:** the insider-threat catch-net. semgrep
security-audit + bandit + custom AST scanner for danger primitives +
Shannon entropy detector for obfuscated payloads + time-bomb
conditional detector. Plus a dual-judge LLM review (TODO).

**False positives are intentional.** This agent is paranoid by design
— a false positive triggers a human review, but a false negative
could let a backdoor onto a live deploy box.

**How it works:**

- `semgrep p/security-audit + p/command-injection + p/insecure-transport`
- `bandit -r app/`
- AST scanner for: `eval`, `exec`, `compile`, `__import__`,
  `subprocess(shell=True)`, suspicious imports (`socket`, `ctypes`,
  `pty`, `paramiko`, `mmap`), env var reads matching
  `KEY|TOKEN|SECRET|PASSWORD`
- Shannon entropy detector for string constants ≥20 chars with
  >4.5 bits/char (warning — base64 / obfuscated payloads)
- Time-bomb pattern: comparisons of `gethostname()`, `uname()`,
  `datetime.now()`, `date.today()` against constants (ERROR — classic
  "behave differently in production" pattern)

**If you triggered this and you weren't trying to be malicious**:

- Most common legitimate triggers are dynamic string construction
  (looks like URL building), env var reads with secret-name patterns
  (looks like exfil), or imports of `socket` etc. for legitimate
  reasons.
- Mention what you were trying to do in the PR description and an
  instructor will manually review.
- The auto-created `security-review` issue tags the instructor — you
  don't need to do anything special, the workflow handles
  notification.

**If you were trying to be malicious**: please don't. The defenses
keep going past this gate (egress firewall, container hardening,
output filter, locked core), and you won't actually compromise
anything. But you'll have wasted everyone's time including your own.

---

## When to use the helper script

```bash
./scripts/explain-failure.sh                 # explains current branch's PR
./scripts/explain-failure.sh 42              # explains PR #42
./scripts/explain-failure.sh code-quality    # explains a specific agent
./scripts/explain-failure.sh --list          # lists all 9 agents
```

## When to use preflight

```bash
./scripts/preflight.sh           # ~15s, every push
./scripts/preflight.sh --full    # ~90s, before opening a PR
```
