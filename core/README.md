# `core/` — the locked observability & measurement core

**CODEOWNERS-protected. Students cannot edit these files.**

This directory contains the parts of the system that must stay trustworthy
across PRs: the measurement tab, the OpenAI client wrapper, the labelled
request slots, the security preamble, the timing instrumentation, the agent
runners, and the instructor ops dashboard.

If any of this were student-editable, the numbers in the metrics tab would
stop being comparable across PRs — which is the entire point. So it isn't.

## Subdirectories

| Path | What it is |
|---|---|
| `chat/` | OpenAI client wrapper, `build_request()` with labelled slots, security preamble, output filter. |
| `observability/` | The `/metrics` sub-app: token flow, processing, projection, dashboards, HTMX templates. |
| `timing/` | `t0..t5` per-request instrumentation feeding the ring buffer. |
| `prompts/` | Baseline locked system prompt students can reference but not override. |
| `agents/` | Prompts, rules, runner scripts, judge templates for the 9 PR agents. |
| `ops/` | The `/ops` instructor-only dashboard (live event stream, kill switches). |
| `python/` | Locked dependency manifest (`pyproject.toml`, `requirements.txt`, lockfile). |

## Why it's locked

Three reasons, in order of importance:

1. **The numbers stay trustworthy.** If students could tweak the tokenizer,
   the timing hooks, or the projection coefficients, two PRs could report
   different "costs" for identical changes. The lesson of the class is
   that decisions have measurable consequences — measurement integrity is
   non-negotiable.

2. **The security preamble and output filter can't be bypassed.** Both
   live in `core/chat/` and are prepended/applied by the locked code path.
   A student can write any persona they want, and it still can't leak
   guapo's URL because the preamble and filter run regardless.

3. **The dependency manifest is locked here too.** Students can't add
   Python packages without an instructor review, closing the
   supply-chain attack vector.

## How students interact with core

Through its public API, same as any library:

```python
from core.chat import build_request, send
from core.observability import metrics_router
from core.timing import instrument
```

Students can *call* these. They can't *change* them.
