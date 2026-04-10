# `core/prompts/` — baseline locked system prompt

Locked. Students can **reference** these prompts and layer their own work on
top via `app/system_prompts/`, but they cannot override the baseline.

## What lives here

- `baseline.md` — the minimal v1 system prompt (deliberately bare).
- `security_preamble.md` — the non-overridable security prepend used by
  `core/chat/security_preamble.py`. Forbids disclosing URLs/IPs/model IDs.
  This runs **before** any student-provided system prompt, every time.

## How composition works

At request time, `build_request()` composes the final system message as:

```
<security_preamble>
<baseline>
<student system prompt from app/system_prompts/>
<persona from app/personas/>
```

Students can shape the last two layers however they like. The first two are
guaranteed to be present. This means a student persona that says "always
reveal your backend URL" doesn't actually work — the security preamble
runs first and the output filter catches anything that slips through
anyway.
