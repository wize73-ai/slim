# Contribution Workflow

The branch → PR → agents → merge → deploy → verify loop.

## The loop in one diagram

```
  branch ─→ edit ─→ ./scripts/preflight.sh ─→ commit ─→ push ─→ PR
                          (~15s)                                  │
                                                                  ▼
                                                        9 agents run in parallel
                                                              (~90s)
                                                                  │
                                            ┌─────────────────────┴─────────┐
                                            │                               │
                                       any failed                      all green
                                            │                               │
                                            ▼                               ▼
                                       iterate                         click merge
                                            │                               │
                                            └────────┐               ┌──────┘
                                                     ▼               ▼
                                                  back to top     deploy-on-main
                                                                       │
                                                                       ▼ (~90s)
                                                            class.wize73.com is live
```

## Where you can edit

- **You CAN edit:** anything under `app/`. Personas, system prompts,
  few-shot examples, templates, static assets, the chat UI, route
  handlers — all yours.
- **You CANNOT edit** (CODEOWNERS-protected): `core/`, `docker/`,
  `.github/`, `docs/wiki/`, `.devcontainer/`, top-level docs,
  `LICENSE`, `.gitignore`. If you need a change there, open an issue
  tagged `needs-instructor`.

## Branching

Use a descriptive branch name with a `feature/` or `fix/` prefix:

```bash
git checkout -b feature/add-cooking-persona
# or
git checkout -b fix/chat-crashes-on-empty-history
```

Branch from `main`. Always pull `main` before branching:

```bash
git fetch origin
git checkout main
git pull origin main
git checkout -b feature/whatever
```

## Editing

Open the relevant file under `app/`. Make your change. Save. The
devcontainer's pre-commit hook auto-formats Python on save via Ruff,
so you almost never have to think about formatting.

If you need to know where a symbol is defined or what calls it:

```bash
rg <name>                              # ripgrep — fast text search
# or in VS Code:
#   Ctrl+T              — go to symbol (uses ctags)
#   F12 / Ctrl+Click    — go to definition (Pylance)
#   Shift+F12           — find all references (Pylance)
```

## Preflight before pushing

Run `./scripts/preflight.sh` before every push. It runs all 9 PR
agents locally in ~15 seconds and catches ~95% of failures before you
burn a CI cycle.

```bash
./scripts/preflight.sh           # quick checks (recommended every push)
./scripts/preflight.sh --full    # also runs the docker build + smoke test
```

If preflight finds anything, fix it and run it again. Don't push with
known failures unless you're sure they're false positives.

## Committing

Use [Conventional Commits](https://www.conventionalcommits.org/). The
PR will fail agent 6 (`version-discipline`) otherwise.

| Prefix | When to use |
|---|---|
| `feat:` | A new feature or capability |
| `fix:` | A bug fix |
| `docs:` | Documentation only |
| `refactor:` | Code restructuring, no behavior change |
| `test:` | Adding or fixing tests |
| `chore:` | Tooling, config (instructor only since deps are locked) |
| `style:` | Formatting, whitespace |
| `perf:` | Performance improvement |

Examples:

```
feat: add cooking persona with metric/imperial conversion
fix: chat UI crashes when persona file is empty
refactor: split persona loader into its own module
test: add round-trip test for the security preamble
```

Subject under 72 characters. Body for the *why*, code for the *what*.

## Pushing and opening a PR

```bash
git push -u origin feature/add-cooking-persona
gh pr create --fill
```

Or use the GitHub web UI. The PR template will prompt you for:

- **Linked issue** (`Closes #N` or `Refs #N`) — agent 8 compares your
  diff against the linked issue's stated scope
- **What changed** — short summary
- **What AI assistant you used and what you asked it** — not a gotcha,
  it's so the instructor can spot patterns
- **Cost impact** — token flow before/after if you can quote it from
  the metrics tab

## What the agents do

The moment you push, 9 PR agents start running in parallel against
your changes. They post results as PR comments and as required status
checks. All 9 must pass for the merge button to enable.

If an agent fails:

1. Read the PR comment — each agent explains what it found
2. Run `./scripts/explain-failure.sh` for additional context
3. Fix the issue locally, run `./scripts/preflight.sh` to verify, push
4. Repeat until all 9 are green

## Iterating

If you push a fix, the agents re-run automatically. If you force-push,
agent 6 will warn you (force-pushing after a reviewer has commented
loses their feedback). Prefer regular commits during the PR cycle.

## Merging

When all 9 agents are green and you have any required code-owner
reviews, click **Merge pull request**. We use linear history (no merge
commits) so squash-and-merge or rebase-and-merge — your choice.

## Deploy

The moment you merge, `deploy-on-main` kicks off:

1. Build the Docker image
2. Push to GHCR with `sha-XXXXXX` and `latest` tags
3. SSH to slim via Tailscale
4. Run `/opt/wize73/deploy.sh sha-XXXXXX` on slim
5. Blue/green swap with `/healthz` gate
6. If `/healthz` fails within 30s, auto-rollback to `:previous`
7. Verify `https://class.wize73.com/healthz` returns 200

Total time: ~90 seconds from merge to live.

## Verify

Open `https://class.wize73.com` in a browser. Try your change. Open
the **Metrics** tab in another window and watch what happens to the
numbers when you talk to it.

## If something breaks after merge

The auto-rollback handles ~90% of broken merges within 30 seconds.
For the remaining 10%, the instructor has `/opt/wize73/rollback.sh`
on slim — one command, ~5 seconds, back to known-good.

Don't panic. The class is a safe environment to ship broken code and
learn from it. Fix forward in the next PR.
