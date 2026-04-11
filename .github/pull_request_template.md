<!--
  Hi! Before opening this PR, run `./scripts/preflight.sh` to catch
  ~95% of agent failures locally. Saves a CI cycle.

  Fill in the sections below — the agents read most of these fields.
-->

## What changed

<!-- One paragraph describing what this PR does. -->

## Linked issue

<!-- "Closes #N" or "Refs #N" — agent 8 (slop-and-scope) compares
     your diff against the linked issue's stated scope. -->

Closes #

## AI assistant collaboration

<!-- Not a gotcha. Instructors use this to spot patterns across the
     class. Be honest. If you didn't use one, say so. -->

- **Tool used**:
  <!-- Claude / ChatGPT / Cursor / Copilot / Gemini / none / other -->
- **What you asked it**:
  <!-- One sentence: "asked Claude to write a YAML schema for personas" -->
- **What you changed manually after**:
  <!-- "fixed three typos and renamed a field" -->

## Cost impact

<!-- The whole point of the class. Open the metrics tab on the
     deployed app and quote what your change does to per-turn token
     flow. If your change is too small to measure (file edit only),
     write "no measurable impact". -->

| | before | after | delta |
|---|---|---|---|
| input tokens / turn | | | |
| output tokens / turn | | | |
| TTFT (ms) | | | |
| context fill % at turn 10 | | | |

<!-- Or in prose: "this adds ~80 tokens per turn from the new
     persona, paid for the rest of every session". -->

## Test plan

- [ ] `./scripts/preflight.sh` runs clean locally
- [ ] All 9 PR agents pass in CI
- [ ] Verified the change in the metrics tab on the deployed PR
- [ ] (if applicable) wiki page updated

## Notes for the reviewer

<!-- Anything that would help the next person understand WHY you made
     this choice. Optional but appreciated. -->
