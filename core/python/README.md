# `core/python/` — locked dependency manifest

Locked. **Students cannot add dependencies.**

## What lives here

- `pyproject.toml` — project metadata, ruff strict ruleset, mypy strict config,
  pytest config, interrogate thresholds.
- `requirements.txt` — pinned production dependencies.
- `requirements-dev.txt` — pinned dev/test dependencies.
- `uv.lock` (or equivalent lockfile) — full transitive dependency graph,
  hash-verified.

## Why it's locked

The single most valuable defense in the security stack. Locking deps here:

- **Kills the supply-chain attack vector.** Students cannot add a typo-squatted
  package, a git-URL dep, or an outdated CVE-ridden library. If they need a
  new package, they file an issue and an instructor adds it after review.
- **Makes builds reproducible.** Pinned + locked means two students running the
  same commit get bit-identical dependency trees.
- **Forces dependency justification.** Needing an instructor review to add
  `requests` for a one-line HTTP call makes the student ask "do I really need
  this?" — which is usually "no."

## Adding a dependency (instructor workflow)

1. Student opens an issue tagged `needs-dep`.
2. Instructor reviews the justification.
3. If approved, instructor adds to `requirements.txt` (or `-dev.txt`),
   regenerates the lockfile, opens a PR, and merges after the agents pass.
4. Student rebases and pulls in the new dep.

## Why not `poetry` or `pipenv`?

`uv` is dramatically faster and produces deterministic lockfiles with hash
verification, which matters for the security posture. Standard `pip-tools`
output works too. We pick whichever the devcontainer can install fastest —
the lockfile format is what matters, not the tool.
