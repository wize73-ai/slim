# Your First PR

A walkthrough of a tiny safe additive change end-to-end. Doing this
once before you tackle a real feature calibrates you to what the
agents look at and how the loop feels.

## The exercise

You're going to add a single persona file. That's it. No code, no
templates, no logic. Just a YAML file under `app/personas/`. The
purpose is to walk the loop with the smallest possible change so all
the moving parts become familiar.

## Step 1 — open the codespace

In the GitHub repo:

1. Click the green **Code** button
2. Click the **Codespaces** tab
3. Click **Create codespace on main**

Wait ~30 seconds. A browser-based VS Code opens with the repo
already cloned, Python set up, and all dependencies installed. The
post-create script printed an orientation banner in the terminal —
read it.

## Step 2 — branch

In the terminal panel:

```bash
git checkout -b feature/cooking-persona
```

Use a descriptive branch name. The agents don't enforce naming but
your future self will thank you.

## Step 3 — create the persona file

Create a new file at `app/personas/cooking.yaml`:

```yaml
name: Cooking Assistant
description: >
  A friendly home cook who specializes in weeknight dinners and
  explains techniques as well as recipes.
tone: warm, practical
constraints:
  - Prefer metric with imperial in parentheses
  - Never suggest raw eggs or raw pork
  - If asked about nutrition, recommend checking with a professional
style_examples:
  - "Let's start by getting the pan hot — really hot, like drops-of-water-dance hot."
  - "I won't tell you this is quick if it isn't."
```

Save it.

**Important:** in v1 the dumb chatbot doesn't actually USE personas
yet. Wiring up persona loading is a separate feature. This first PR
just adds the file. Subsequent PRs can pick it up.

## Step 4 — preflight

Before pushing, run the local agent suite:

```bash
./scripts/preflight.sh
```

Output should look like:

```
══ 1/9  version-discipline ══
  ✓ requirements.txt fully pinned
  ✓ no edits to CODEOWNERS-locked paths
  ✓ last commit subject is conventional: "..."

══ 2/9  code-quality ══
  ✓ ruff format (no diffs)
  ✓ ruff check (no lint issues)
  ...

✓ preflight passed (14s)
```

If anything fails, read the output and fix it. The most common first-
PR failure is a non-conventional commit message. Run `git commit --amend`
to fix.

## Step 5 — commit

```bash
git add app/personas/cooking.yaml
git commit -m "feat: add cooking persona with weeknight-dinner focus"
```

Conventional commit format: `feat: <one-line description>`. Subject
under 72 characters. The agents enforce this.

## Step 6 — push and open the PR

```bash
git push -u origin feature/cooking-persona
gh pr create --fill --base main
```

Or via the web UI. Either way, fill in the PR template:

- **Linked issue**: if there's a backlog issue for this, write
  `Closes #N`. If there isn't, write `(no linked issue — first PR
  walkthrough)` and mention the agent 8 warning is expected.
- **What changed**: "Adds a single cooking persona YAML file."
- **AI assistant**: write what you used. Even "didn't use one,
  copied from the wiki example."
- **Cost impact**: "None — file isn't loaded by anything yet."

## Step 7 — watch the agents

Within ~90 seconds the 9 PR agents start posting their results as
status checks at the bottom of the PR. Click **Details** on each one
to see the workflow log.

For your first PR, expect:

- ✅ `secrets-scan` — passes (no URLs in your file)
- ✅ `code-quality` — passes (no Python changed)
- ✅ `red-team` — passes (the persona isn't loaded yet, can't break it)
- ✅ `blue-team` — passes (no code changes)
- ✅ `classroom-safety` — passes (your persona has nothing inappropriate)
- ✅ `version-discipline` — passes if your commit is conventional
- ✅ `build-and-smoke` — passes (image still builds, metrics tab still works)
- ⚠️ `slop-and-scope` — passes with a warning ("PR isn't linked to an issue")
- ✅ `malicious-code-review` — passes (nothing dangerous in YAML)

If anything actually fails (not just warns), read the agent's PR
comment and run `./scripts/explain-failure.sh` for guidance.

## Step 8 — merge

When all 9 are green (warnings are OK, only failures block), click
**Merge pull request**. We use linear history — pick squash or rebase.

## Step 9 — watch the deploy

After merging, click **Actions** at the top of the repo. The
`deploy on main` workflow should be running. It takes ~90 seconds:

1. Build the Docker image (~30s with cache)
2. Push to GHCR (~5s)
3. SSH to slim via Tailscale (~3s)
4. Run `deploy.sh` blue/green swap (~30s including health gate)
5. Verify the public URL (~5s)

Watch each step's check mark turn green. If any fail, the auto-
rollback engages and you see the failure in the workflow log.

## Step 10 — verify it's live

Open `https://class.wize73.com` in a new tab. The chatbot should
work. Your persona file is on disk inside the running container — it
just isn't being used yet because the v1 chatbot doesn't load
personas.

Open `https://class.wize73.com/metrics` in another tab. Have a chat
turn or two. Watch the per-turn pyramid bar show up.

## What you just learned

- The codespace startup takes ~30 seconds
- A trivial file-only PR takes ~3 minutes from branch to live
- The 9 agents run in parallel and complete in ~90 seconds total
- The deploy runs in ~90 seconds
- Total branch-to-live cycle: ~5 minutes

You now have a calibrated sense of the loop. Real feature work feels
the same shape, just with more iteration on the agents.

## What to do next

Pick a starter issue from the [Feature Backlog](07-Feature-Backlog).
Start with one tagged `easy` if it's your first time doing actual
implementation. Read the [Agents Reference](05-Agents-Reference) so
you know what each one wants from you.

Most importantly: **keep the metrics tab open while you work**.
Watching numbers move is the whole point of the class.
