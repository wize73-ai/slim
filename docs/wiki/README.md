# `docs/wiki/` — source of truth for the GitHub Wiki

Locked. Hand-curated static markdown, not auto-generated. Synced to the
repo's GitHub Wiki by a post-merge action.

## Pages

| File | Title |
|---|---|
| `Home.md` | Landing page |
| `01-Architecture.md` | Three-host topology, locked core, bidirectional framing diagram |
| `02-Contribution-Workflow.md` | Branch → PR → agents → merge → deploy → verify |
| `03-Bidirectional-Framing.md` | The central mental model with worked examples |
| `04-Your-First-PR.md` | Step-by-step walkthrough of a safe additive change |
| `05-Agents-Reference.md` | One page per agent: what it checks, why, how to fix failures |
| `06-Troubleshooting.md` | Rollback, common agent failures, deploy failures, metrics tab issues |
| `07-Feature-Backlog.md` | Pre-curated starter issues at graduated difficulty |

## Editing

The wiki is CODEOWNERS-protected. Students who spot typos or unclear
explanations should open an issue tagged `wiki` and the instructor will
fix it.

## Why not auto-generated

An earlier design had GitNexus generating the architecture page on every
merge. That was dropped because it adds a dependency and the curation
burden of hand-maintaining ~8 pages is low. Simpler wins.
