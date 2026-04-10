# `core/chat/` — OpenAI-compatible client wrapper

Locked. Built against guapo's frozen [INTERFACE.md](../../../personal/speech-service/INTERFACE.md).

## What lives here

- `client.py` — factory that reads `OPENAI_BASE_URL` and `OPENAI_API_KEY` from
  environment at runtime. The URL is **never** hardcoded in source. Guapo's
  address lives only on the deploy box.
- `build_request.py` — constructs the messages array from **labelled slots**:
  `build_request(system, persona, examples, history, user)`. The labelling is
  what makes the token-flow decomposition in the metrics tab possible.
- `security_preamble.py` — a non-overridable prepend on every system prompt
  instructing the model to never disclose URLs, IPs, model IDs, or hostnames.
  Students can write any persona they like; this still runs first.
- `output_filter.py` — regex-redaction of guapo identifiers (`phi-4-mini`,
  `xtts_v2`, `192.168.1.103`, `100.91.130.128`, `guapo`, etc.) from every SSE
  chunk before it reaches the browser. Belt and suspenders for the preamble.
- `errors.py` — structured error handling with graceful degradation when guapo
  returns 5xx. The chat UI shows a friendly banner; the logs capture detail.

## The contract students depend on

```python
from core.chat import build_request, stream_completion

messages = build_request(
    system=load_locked_system_prompt(),  # from core.prompts
    persona=load_persona("cooking"),     # from app/personas/
    examples=load_examples("cooking"),   # from app/examples/
    history=session.history,             # from session state students manage
    user=user_message,                   # current input
)

async for token in stream_completion(messages):
    yield token  # already filtered by output_filter
```

The token-flow decomposition in the metrics tab reads the labelled slots
directly from the `build_request` call, which is why students can't
short-circuit it with a raw `messages=[...]` list.
