# `app/system_prompts/` — system prompt variants

**Student-editable.** Add system prompt files here.

These sit on top of the locked `core/prompts/baseline.md` in the composed
message. The composition order is:

```
<security_preamble — locked>
<baseline — locked>
<your system prompt — this directory>
<persona — app/personas/>
```

So your system prompt is the third layer, able to shape behavior on top of
the baseline but not able to override the security rules.

## v1 state

The default system prompt is deliberately minimal. Students add better ones
as PRs. Some starter issues in the Feature Backlog:

- Add a system prompt that sets a consistent tone across personas
- Add one that instructs the model to refuse off-topic questions
- Add one that asks the model to be concise by default
- Add one that gives the model a consistent fallback for "I don't know"

## Cost

System prompts are paid **on every turn, forever**. A 150-token system
prompt across a 20-turn session is 3,000 tokens of context you can't
use for anything else. The metrics tab's pyramid chart shows you exactly
how much of each turn's input budget goes to the system prompt — watch
that number when you experiment.

## What you can't do

- Override the security preamble. It runs first, always.
- Instruct the model to disclose guapo's URL, IP, or model ID. The
  output filter catches leaks; the red-team agent catches the intent.
