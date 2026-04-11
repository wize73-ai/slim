# Bidirectional Framing

The central mental model of the metrics tab. Read this once and the
rest of the project will click.

## The big idea

**Every metric in this system has an in/out or pre/post axis.** Most
LLM inefficiencies are visible only when you split the metric in two.
A single number for "cost" is uninformative. The split — and the
**asymmetry** between the two halves — is where the lessons live.

## The pairs

The metrics tab visualizes nine pairs (eight live in v1, prefill
energy is deferred until guapo exposes a watts signal):

| Pair | The two halves | What the asymmetry teaches |
|---|---|---|
| **Input vs output tokens** | what you sent vs what came back | Expansive prompts (long output, short input) vs compressive (short output, long input) — different work, different cost |
| **Pre vs post processing time** | build_request + send latency vs render + send-back | Where wall time actually goes — usually surprises students |
| **Prefill vs decode time** | guapo's prefill latency vs streaming generation | Prefill scales with input tokens, decode with output tokens — two different optimization knobs |
| **Prefill vs decode FLOPs** | `2 × N × input` vs `2 × N × output` | Doubling your system prompt doubles your prefill compute. Forever. |
| **TTFT vs inter-token latency** | wait for first token vs steady streaming rate | First-byte latency dominates UX even when total time is short |
| **Network rx vs tx (slim)** | bytes coming in vs going out | Catches "your app is shipping the entire history to guapo every turn" |
| **Cumulative input growth vs output growth** | mirrored stacked area chart | History bloat made visible — watch input balloon while output stays flat |
| **Input vs output token asymmetry scatter** | (input_tok, output_tok) per turn with y=x line | Reveals what KIND of work you're asking the model to do; personas tend to cluster |

## Token flow decomposition

The pyramid bar chart on the metrics tab decomposes each turn's
**input** into the labelled slots that fed it:

```
turn 7 input (453 tokens):
[system 84][persona 62][examples 110][history 178][user 19]
            ↓                ↓             ↓          ↓
       paid every turn   paid every     grows         the only
       (locked + your     turn          monotonically  per-turn
        overlay)                                       variable
```

This is the most actionable chart in the whole project. When you add
a feature, you can see *exactly* which slot grew and by how much.

## What "system" includes

The `system` slot in the bar is the **composed** system message:

```
<security preamble — locked, ~280 tokens>
<baseline — locked, ~190 tokens>
<your system prompt overlay — initially empty, you fill it in>
<your persona — initially empty, you fill it in>
```

So the system slot starts at ~470 tokens before you add anything.
When you add a 60-token persona, the system slot grows to ~530 — that
60 token addition is paid on every turn for the rest of the session.

The metrics tab tracks the persona's contribution **independently**
even though it's embedded in the system slot, so you can see how much
your persona alone is costing.

## Why "asymmetry"

The asymmetry between the two halves of any pair is the diagnostic
signal. Examples:

- **Input >> output** with high prefill time and low decode time:
  you're asking the model to do compressive work (summarizing,
  classifying, extracting). Cost mostly in prefill.
- **Input << output** with low prefill and high decode: expansive
  work (writing, brainstorming, code generation). Cost mostly in
  decode.
- **Input == output** with mostly even time split: conversational
  back-and-forth. The "neutral" zone.

A persona that compresses (summarization assistant) clusters in one
quadrant of the asymmetry scatter chart. A persona that expands
(creative writer) clusters in the opposite quadrant. Watch the
clustering.

## A worked example

Suppose you start with an empty chatbot and add a 200-token persona.
Then you have a 5-turn conversation where each user message is
~25 tokens and each assistant reply is ~80 tokens.

**Per-turn costs:**

| Turn | system | persona-as-part-of-system | history | user | output | total in | total out |
|---|---|---|---|---|---|---|---|
| 1 | 670 | 200 | 0 | 25 | 80 | 695 | 80 |
| 2 | 670 | 200 | 105 | 25 | 80 | 800 | 80 |
| 3 | 670 | 200 | 210 | 25 | 80 | 905 | 80 |
| 4 | 670 | 200 | 315 | 25 | 80 | 1010 | 80 |
| 5 | 670 | 200 | 420 | 25 | 80 | 1115 | 80 |

The system slot is **the same 670 tokens every turn**. The 200-token
persona contribution is paid 5 times = **1000 tokens of persona cost
across the session**. The history grows linearly. By turn 5, the
input is 1.6× what it was on turn 1.

If you cut the persona to 80 tokens, you save 600 tokens across the
session. If you cut history retention from 5 turns to 3, you save
~210 tokens by turn 5. Both changes are visible immediately in the
metrics tab.

This is why the projection calculator exists: enter your planned
persona/system/history sizes and see the curves before you actually
spend the time to implement.

## Bidirectional ≠ "two charts"

A common misunderstanding: bidirectional doesn't mean "show two
charts side by side." It means **the chart's structure encodes the
in-vs-out relationship directly.**

- The **pyramid bar** shows input on the left of zero, output on
  the right, with a clear asymmetry at the center.
- The **mirrored cumulative area** has input above zero growing up
  and output below zero growing down — the gap between them IS the
  asymmetry trajectory.
- The **scatter** has input on x and output on y with `y=x` as the
  reference; points above the line are output-heavy, below are
  input-heavy.

The structure is the message.

## What the tab shows you, in priority order

If you open the metrics tab and only have time to look at one thing,
look at the **pyramid bar for the most recent turn**. It tells you:

1. How much your fixed cost is (system + persona + few-shots)
2. How much your variable cost is (history + user)
3. How much you got back (output)
4. Whether your asymmetry is what you intended

Then look at the **cumulative trajectory** to see how those numbers
evolve across the session.

Then run the **projection calculator** to model what your *next*
change would do before you make it.

That's the loop. The point of the class is to make it second nature.
