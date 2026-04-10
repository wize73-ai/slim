# `app/personas/` — persona definitions

**Student-editable.** Add your own persona files here as YAML or JSON.

## Format (proposed — define this in your first PR if you want)

```yaml
# cooking.yaml
name: Cooking Assistant
description: >
  A friendly home cook who specializes in weeknight dinners and explains
  techniques as well as recipes.
tone: warm, practical
constraints:
  - Prefer metric with imperial in parentheses
  - Never suggest raw eggs or raw pork
  - If asked about nutrition, recommend checking with a professional
style_examples:
  - "Let's start by getting the pan hot — really hot, like drops-of-water-dance hot."
  - "I won't tell you this is quick if it isn't."
```

The persona file is consumed by `build_request()` in `core/chat/`, which
injects it into the `persona` slot of the labelled message construction.
That means the metrics tab can show you exactly how many tokens your
persona costs per turn — and help you optimize it.

## Tips

- **Short personas are usually better.** Every token in your persona is paid
  on every turn, forever. A 200-token persona with a 10-turn session = 2000
  tokens you could have spent on user input or response content.
- **The token-flow chart in the metrics tab tells you the truth.** If your
  persona doubles your per-turn cost, you'll see it.
- **Test with the red-team probes.** Agent 3 runs 12 probes against your
  persona on every PR. Personas that break under pressure get flagged.

## What you can't do

- Leak URLs, IPs, model IDs, or hostnames. The security preamble in
  `core/chat/` prevents this. Your persona cannot override it.
- Embed instructions that tell the model to bypass the preamble. The
  output filter catches the leaks; the red-team agent will catch the
  intent.
