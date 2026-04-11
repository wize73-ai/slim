# Feature Backlog

A pre-curated set of starter issues at graduated difficulty. Each is
sized to be a single PR that ships in one sitting. Pick one that
matches your time and your interests.

The dumb v1 chatbot deliberately has nothing. Every item below moves
it from "barely works" to "actually useful" — and every one of them
shows up immediately in the metrics tab.

## Difficulty rubric

- **★ easy** — file edit only, no Python. ~15 minutes.
- **★★ medium** — small Python change, one or two files. ~30-60 minutes.
- **★★★ hard** — multiple files, cross-cutting, requires understanding
  the labelled-slot architecture. ~1-2 hours.
- **★★★★ stretch** — touches the edge of what's possible without
  unlocking core/. Discuss with instructor first.

## ★ easy

### Add a persona

Create one new file under `app/personas/`. Pick a domain (cooking,
debugging, writing, math, history, music, fitness, gardening...).
The format isn't enforced yet — you can establish it. Keep the
persona under ~150 tokens because every token is paid every turn.

The PR is just the file addition. Wiring up loading is a separate
feature (see medium tier).

### Add a few-shot example block

Same as above but under `app/examples/`. Two or three (user,
assistant) exchanges that show the kind of style you want.

### Improve the dumb v1 chat UI

Edit `app/templates/chat.html`. Anything is fair game: better
typography, a header, a footer, a token counter chip on the input
field, a button to clear the response. Use HTMX where you need
interactivity — no JS framework needed.

### Add an issue template for your favorite kind of PR

Edit `.github/ISSUE_TEMPLATE/`. Open the file in your branch, look
at the existing templates, add a new one. (Note: `.github/` is
locked, so this needs an instructor approval.)

## ★★ medium

### Wire up persona loading

Make the chatbot actually USE files in `app/personas/`. Add a
`load_persona(name)` helper in `app/main.py` that reads the YAML
and returns the text. Pass it to `build_request(persona=...)`. Add
a query parameter or form field to pick the persona.

After this lands, the metrics tab's pyramid bar will show the
persona's tokens as a separate slot.

### Add a system prompt editor

Add a textarea on the chat page that lets the user override the
system prompt for the next turn. POST it as a form field. Pass it
to `build_request(student_system=...)`. The metrics tab will show
the new tokens flowing.

### Add conversation history retention

Currently each chat turn is independent. Add a session that retains
the last N turns. Store it in memory keyed by a session id (a cookie
or a query parameter). Pass it to `build_request(history=...)`.

This is the feature that most dramatically affects the metrics —
watch the cumulative trajectory chart go from flat to ramping.

### Add a temperature slider

Slider on the chat page from 0.0 to 2.0. Pass to
`stream_completion(temperature=...)`. Watch how the projection
calculator's coefficients shift when temperature changes the
deterministic-vs-creative trade-off.

### Add response streaming

Currently the chat handler waits for the full response then returns
HTML. Convert it to an SSE stream so tokens appear as they arrive.
HTMX has `hx-ext="sse"` for this. The TTFT vs inter-token chart in
the metrics tab finally has data when this lands.

### Add an error banner that explains what went wrong

When the chat handler hits an `UpstreamUnavailable` or `UpstreamTimeout`
or `FilterBlocked`, the v1 just shows a generic "service unavailable"
message. Improve it: different messages for different errors,
suggested actions, link to the metrics tab to verify the inference
host status.

## ★★★ hard

### Add voice input

The whisper STT endpoint is on guapo's frozen surface. The chatbot
can call `client.audio.transcriptions.create(file=...)` against the
same `OPENAI_BASE_URL`. Add a microphone button to the chat UI that
records via the browser's MediaRecorder API, posts the audio to a
new `/transcribe` route, and inserts the transcribed text into the
input box.

### Add voice output

Same idea, other direction. Add a "play" button next to assistant
responses that calls a new `/speak` route, which proxies to
`client.audio.speech.create(input=...)` and returns the WAV. Use
the browser's `<audio>` element to play it.

Watch the metrics tab — the network bytes panel shows audio traffic
as a different color than text traffic.

### Add a persona picker dropdown

A dropdown on the chat page populated from `app/personas/` (read
the directory at request time, return a list). Selection persists
in a cookie. Different personas have different per-turn cost — show
this in the metrics tab by tagging the turn record with the persona
name and adding a per-persona breakdown.

### Add a content filter on user input

Before passing the user message to `build_request()`, check it
against a small profanity / harmful-content filter. Reject (return
an error banner) or sanitize (replace flagged words with `[redacted]`).
This is a defensive PR — it'll please agent 4 (blue-team) by
adding visible input validation.

### Add token budget warnings

When a session approaches the 8192-token context wall, show a banner
in the chat UI: "you're at 80% of context, history will be trimmed
soon" → "you're at 95%, the next turn will lose oldest history" →
"context full, the model is forgetting older turns". Use the
projection calculator's coefficients to estimate when the wall hits.

### Add a "compare two prompts" view

Two textareas side by side. User submits, the chatbot runs the same
input against each, shows both responses next to each other. Add a
diff view of the metrics — which version cost more, which was faster,
which used more output tokens.

This is one of the most pedagogically valuable features and makes
"what does this design choice cost" tangible.

## ★★★★ stretch

### Add a session-replay view

Pick any session from the metrics ring buffer and replay it to the
user — the chat exchange plus the metrics curve scrubbing. This
needs a small data model for sessions and probably a SQLite database
in a named volume (out of scope for the dumb v1).

### Add multi-persona conversation simulation

Two personas talking to each other instead of a user talking to one.
The chat handler runs in a loop: persona A generates a turn, feed
it as input to persona B, etc. Watch the asymmetry scatter chart
explode with both personas' turn-by-turn distributions.

### Add a "what would this PR cost?" preview

When you save a file in the codespace, run a tiny script that
projects what your changes would do to the metrics tab — using the
projection calculator API and a synthetic conversation. Display the
projection as a notification in VS Code.

### Add a per-class leaderboard

Track which students' chatbots have the best asymmetry ratio for a
given task. Run a fixed prompt against every recently-deployed
container, score the responses, post the leaderboard to the ops
dashboard. Competition + measurement = motivation.

## Adding your own backlog item

If you have an idea that isn't here, open an issue with the template:

- One-line title
- Difficulty estimate
- What metric it should affect
- Why it's pedagogically interesting

Get the instructor's blessing before implementing if it touches the
locked core or requires new dependencies.

## Reading the metrics tab is the assignment

Whatever feature you build, **the work isn't done until you can
articulate what it cost**. Open the metrics tab, take a screenshot
of the per-turn pyramid before and after, write a one-paragraph
post-mortem in the PR description: "this feature added X tokens per
turn and Y ms of TTFT, and here's why I think the trade-off is
worth it (or isn't)."

That's the actual learning. Shipping is just the medium.
