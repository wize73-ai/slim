# `scripts/` — developer helper scripts

Pre-installed in the Codespaces devcontainer and available in any
local checkout.

## Shipped scripts (locked)

| Script | What it does |
|---|---|
| `preflight.sh` | Runs all 9 PR agents locally against your current branch in ~30 seconds. **Use this before every push** — biggest velocity unlock in the whole class. |
| `explain-failure.sh` | Reads the latest failing check run from the PR via `gh` CLI and prints an explanation plus a link to the relevant wiki page. |

The shipped scripts are in the locked core's CI surface and cannot be
edited by students. Think of them as extensions of the agent system.

## Student-added scripts

You can add your own helper scripts to this directory — the top-level
`scripts/` is in the student-editable zone (just not the shipped
filenames above). If you write something useful, open a PR so your
classmates can use it too.

## Symbol navigation without GitNexus

Earlier plans used GitNexus wrappers for "where is this symbol defined"
and "what depends on this file." Per the decision to not use GitNexus in
the pipeline, those use cases are handled by standard tooling that's
pre-installed in the devcontainer:

- `rg` (ripgrep) for text/symbol search — much faster than `grep`
- `ctags` for jump-to-definition
- VS Code's built-in **Outline** and **Find All References** for
  graphical navigation

Use those. They're the tools professional developers use anyway.
