# `app/examples/` — few-shot example blocks

**Student-editable.** Add few-shot examples here.

A few-shot block is a handful of (user, assistant) exchanges that prime the
model for your desired interaction style. They go into the labelled
`examples` slot of `build_request()` so the metrics tab can track their
per-turn cost.

## Format (proposed — define this in your PR if you want)

```yaml
# cooking.yaml
persona: cooking   # which persona these examples pair with
examples:
  - user: "I only have pasta and a can of tuna. Now what?"
    assistant: >
      Tuna pasta in five minutes. Boil the pasta. While it boils, drain the
      tuna and flake it into a bowl with olive oil, a squeeze of lemon, and
      black pepper. When the pasta's done, save a splash of cooking water,
      drain the rest, and toss everything together. Add more olive oil if
      it looks dry. Top with parmesan if you have it.
  - user: "What if I don't have lemon?"
    assistant: >
      Vinegar works — white wine vinegar or rice vinegar, a teaspoon. The
      goal is a little acid to cut the richness of the tuna.
```

## Cost reality check

**Every few-shot example is paid on every turn.** Three examples of ~80 tokens
each = 240 tokens per turn *for the rest of the session*. Over a 20-turn
conversation, those examples cost 4,800 tokens. The projection calculator
in the metrics tab lets you model this before you commit.

Use few-shots when the model genuinely needs them — usually for tone or
format, rarely for knowledge. The agent 8 slop-and-scope check will flag
few-shot blocks that add cost without measurable quality improvement.
