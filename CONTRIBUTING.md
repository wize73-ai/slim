# Contributing

Quick reference. Full details live in the [wiki](../../wiki).

## Where you can edit

- **You CAN edit:** anything under `app/` — personas, system prompts, few-shot
  examples, chat templates, static assets. Also `scripts/` for your own
  helpers (but the ones that ship are locked).
- **You CANNOT edit** (CODEOWNERS-protected): `core/`, `docker/`, `.github/`,
  `docs/wiki/`, `.devcontainer/`, top-level docs, `LICENSE`, `.gitignore`.
  If you need a change in those paths, open an issue and tag it
  `needs-instructor`.

## The loop

```
branch → edit → preflight → commit → push → PR → agents → iterate → merge → deploy
                 (~30s)                        (~90s)                      (~90s)
```

1. **Branch** from `main` with a descriptive name:
   `git checkout -b feature/add-cooking-persona`
2. **Edit** files under `app/`.
3. **Preflight**: `./scripts/preflight.sh` runs all 9 PR agents locally in
   ~30 seconds. Fix what it catches before pushing — saves CI cycles and
   makes you look like a pro.
4. **Commit** with a conventional commit message:
   - `feat: add cooking persona with metric/imperial conversion`
   - `fix: chat UI crashes when persona file is empty`
   - `docs: explain the token flow chart in Your First PR`
   - `refactor: split persona loader into its own module`
5. **Push** and open a PR. **Link it to the issue you're solving** in the
   PR description — agent 8 (slop-and-scope) compares your diff against
   the linked issue to flag scope creep.
6. **Agents run in parallel** and post feedback on the PR. There are 9 of
   them. Each explains what it checks and how to fix failures. Read the
   comments before opening `Claude`/`Cursor`/etc. — the fix is usually in
   the comment.
7. **Iterate** until all checks are green.
8. **Merge.** The deploy workflow kicks off automatically and your change
   is live at `class.wize73.com` in ~90 seconds.

## Before your first PR

Read [Your First PR](../../wiki/04-Your-First-PR). It walks through a safe
additive change end-to-end and calibrates you to what the agents look at.
Skipping it means you'll learn the same lessons the hard way, in front of
the class, with live CI feedback.

## Dependencies are locked

**You cannot add new Python packages** to the repo. `core/python/` is
CODEOWNERS-protected. If you genuinely need a new package:

1. Open an issue describing what package and why.
2. Tag it `needs-dep`.
3. An instructor will add it or suggest an alternative.

This cuts off supply-chain attacks and forces every dependency to be
justified. It's how real software teams work.

## AI assistants are welcome, but honest

You will probably use Claude, Copilot, Cursor, Gemini, or ChatGPT to help
write code. **Good.** The PR template asks you to record:

- Which tool you used
- What you asked it
- What you changed manually afterwards

This is **not** a gotcha. It's so instructors can spot patterns across the
class and help everyone collaborate with AI more effectively. Students who
note they copy-pasted a 400-line refactor from Claude without reading it
are not in trouble — they're getting the lesson that "the model suggested
it" is not an answer when the PR agents start finding problems.

## If something breaks after merge

The deploy is **auto-rollback-on-health-check-failure**. Most broken
merges fix themselves within 30 seconds. If something sticks, the
instructor has `rollback.sh` on the deploy box — one command and we're
back to the previous known-good image.

**Do not panic.** The class is a safe environment to ship broken code and
learn from it. That's the whole point.

## Commit message format

We use [Conventional Commits](https://www.conventionalcommits.org/). The
types we accept:

- `feat:` — a new feature or capability
- `fix:` — a bug fix
- `docs:` — documentation only
- `refactor:` — code restructuring, no behavior change
- `test:` — adding or fixing tests
- `chore:` — tooling, config, deps (instructor only since deps are locked)
- `style:` — formatting, whitespace

Agent 6 (`version-discipline`) enforces this on every PR and explains why
it matters when it rejects yours.

## Getting help

- **Agent said something I don't understand:** `./scripts/explain-failure.sh`
  reads the latest failing check run and points at the relevant wiki page.
- **Stuck on a concept:** the [Bidirectional Framing](../../wiki/03-Bidirectional-Framing)
  page explains the core mental model.
- **Stuck on the workflow:** walk through [Your First PR](../../wiki/04-Your-First-PR) again.
- **Stuck on code:** open a draft PR and ask in the PR description. The
  instructor (and your classmates) can see and comment.

## One last thing

The metrics tab at `/metrics` is the feedback loop for everything you do.
**Keep it open in another tab.** When you merge a change, watch what moves.
That's how you learn what each design decision actually costs.
