#!/usr/bin/env bash
# Bulk-create the starter issues from the Feature Backlog wiki page.
#
# Run this ONCE before class to populate the issue queue. Each issue is
# created with the appropriate label, difficulty, and a link back to
# the wiki section.
#
# Re-running creates duplicate issues — guard against that by checking
# `gh issue list --state all --search "<title>"` if you need to be safe.
#
# Usage:
#     bash .github/scripts/create-starter-issues.sh           # create all
#     bash .github/scripts/create-starter-issues.sh --easy    # only easy
#     bash .github/scripts/create-starter-issues.sh --dry-run

set -euo pipefail

REPO="wize73-ai/slim"
WIKI_BASE="https://github.com/wize73-ai/slim/wiki/07-Feature-Backlog"

DRY_RUN=0
TIER_FILTER=""

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --easy) TIER_FILTER="easy" ;;
        --medium) TIER_FILTER="medium" ;;
        --hard) TIER_FILTER="hard" ;;
        --stretch) TIER_FILTER="stretch" ;;
        *) echo "unknown arg: $arg" >&2; exit 1 ;;
    esac
done

if ! command -v gh &>/dev/null; then
    echo "ERROR: gh CLI not installed" >&2
    exit 1
fi

create_issue() {
    local tier="$1"
    local title="$2"
    local body="$3"
    local labels="starter-task,$tier"

    if [[ -n "$TIER_FILTER" && "$tier" != "$TIER_FILTER" ]]; then
        return 0
    fi

    if [[ $DRY_RUN -eq 1 ]]; then
        echo "  [dry-run] [$tier] $title"
        return 0
    fi

    # Check if an issue with this title already exists.
    existing=$(gh issue list -R "$REPO" --state all --search "in:title \"$title\"" --json number --jq '.[0].number' 2>/dev/null || echo "")
    if [[ -n "$existing" ]]; then
        echo "  ✓ already exists as #$existing — $title"
        return 0
    fi

    gh issue create -R "$REPO" \
        --title "$title" \
        --body "$body" \
        --label "$labels" \
        >/dev/null

    echo "  ✓ created — $title"
}

echo "==> creating starter issues for $REPO (filter=${TIER_FILTER:-all}, dry_run=$DRY_RUN)"

# ─── ★ easy ─────────────────────────────────────────────────────────────────

create_issue "easy" "feat: add a persona file (any topic)" \
"Pick a topic you find interesting — cooking, debugging, music, history, fitness, gardening — and write a single persona YAML file under \`app/personas/\`. Keep the persona under ~150 tokens because every token is paid every turn.

This PR is just the file addition. Wiring up loading is a separate feature (see medium tier).

See [Feature Backlog → ★ easy → Add a persona]($WIKI_BASE#add-a-persona) for details.

**Affects:** when persona loading is wired up (separate PR), the metrics tab pyramid will show your persona's tokens as a separate slot."

create_issue "easy" "feat: add a few-shot example block" \
"Add a YAML file under \`app/examples/\` with 2-3 (user, assistant) example exchanges that demonstrate the kind of style you want from the model.

See [Feature Backlog → ★ easy → Add a few-shot example block]($WIKI_BASE#add-a-few-shot-example-block).

**Affects:** when few-shot loading is wired up, the examples slot in the pyramid chart populates."

create_issue "easy" "feat: improve the dumb v1 chat UI styling" \
"Edit \`app/templates/chat.html\`. Anything is fair game: better typography, header, footer, token counter chip, clear button. HTMX where you need interactivity — no JS framework.

See [Feature Backlog → ★ easy → Improve the dumb v1 chat UI]($WIKI_BASE#improve-the-dumb-v1-chat-ui).

**Affects:** the user experience side. Watch network rx/tx in the metrics tab — heavier UI may add static asset traffic."

# ─── ★★ medium ──────────────────────────────────────────────────────────────

create_issue "medium" "feat: wire up persona loading" \
"Make the chatbot actually USE files from \`app/personas/\`. Add a \`load_persona(name)\` helper in \`app/main.py\` that reads the YAML and returns the persona text. Pass it to \`build_request(persona=...)\`. Add a query parameter or form field to pick the persona.

See [Feature Backlog → ★★ medium → Wire up persona loading]($WIKI_BASE#wire-up-persona-loading).

**Affects:** the persona slot in the pyramid bar populates with real tokens. Watch how different personas have different per-turn cost."

create_issue "medium" "feat: add a system prompt editor textarea" \
"Add a textarea on the chat page that lets the user override the system prompt for the next turn. POST it as a form field. Pass to \`build_request(student_system=...)\`.

See [Feature Backlog → ★★ medium → Add a system prompt editor]($WIKI_BASE#add-a-system-prompt-editor).

**Affects:** the system slot in the pyramid bar grows in real time as students type."

create_issue "medium" "feat: add conversation history retention" \
"Currently each chat turn is independent. Add a session that retains the last N turns. Store keyed by a session id (cookie or query parameter). Pass to \`build_request(history=...)\`.

This is the feature that most dramatically affects the metrics tab — watch the cumulative trajectory chart go from flat to ramping.

See [Feature Backlog → ★★ medium → Add conversation history retention]($WIKI_BASE#add-conversation-history-retention).

**Affects:** the history slot in the pyramid bar starts to grow. The cumulative session trajectory chart finally has shape."

create_issue "medium" "feat: add a temperature slider" \
"Slider on the chat page from 0.0 to 2.0. Pass to \`stream_completion(temperature=...)\`.

See [Feature Backlog → ★★ medium → Add a temperature slider]($WIKI_BASE#add-a-temperature-slider).

**Affects:** the projection calculator's coefficients shift when temperature changes the deterministic-vs-creative trade-off."

create_issue "medium" "feat: add SSE response streaming" \
"Currently the chat handler waits for the full response then returns HTML. Convert to an SSE stream so tokens appear as they arrive. HTMX has \`hx-ext=\"sse\"\` for this.

See [Feature Backlog → ★★ medium → Add response streaming]($WIKI_BASE#add-response-streaming).

**Affects:** the TTFT vs inter-token latency chart in the metrics tab finally has data when this lands."

create_issue "medium" "feat: improve error banners with specific messages" \
"The v1 chat handler shows a generic 'service unavailable' for any error. Improve: different messages for UpstreamUnavailable / UpstreamTimeout / FilterBlocked, suggested actions, link to /metrics to verify host status.

See [Feature Backlog → ★★ medium → Add an error banner]($WIKI_BASE#add-an-error-banner-that-explains-what-went-wrong).

**Affects:** UX during failures. Doesn't move the metrics tab directly but improves the recovery loop."

# ─── ★★★ hard ───────────────────────────────────────────────────────────────

create_issue "hard" "feat: add voice input via whisper" \
"The whisper STT endpoint is on guapo's frozen surface. Add a microphone button to the chat UI that records via MediaRecorder, posts to a new \`/transcribe\` route, and inserts the transcribed text into the input box.

See [Feature Backlog → ★★★ hard → Add voice input]($WIKI_BASE#add-voice-input).

**Affects:** the network bytes panel shows audio traffic as a different color than text traffic. Significant per-turn cost increase."

create_issue "hard" "feat: add voice output via XTTS" \
"Add a play button next to assistant responses. New \`/speak\` route proxies to \`client.audio.speech.create\` and returns the WAV. Use \`<audio>\` element to play.

See [Feature Backlog → ★★★ hard → Add voice output]($WIKI_BASE#add-voice-output).

**Affects:** same as voice input — audio traffic in the network panel."

create_issue "hard" "feat: persona picker dropdown with per-persona metrics" \
"Dropdown on the chat page populated from \`app/personas/\` (read directory at request time). Selection persists in cookie. Tag each turn record with the persona name, add a per-persona breakdown to the metrics tab.

See [Feature Backlog → ★★★ hard → Add a persona picker dropdown]($WIKI_BASE#add-a-persona-picker-dropdown)."

create_issue "hard" "feat: add a content filter on user input" \
"Before passing the user message to \`build_request()\`, run it through a small profanity / harmful-content filter. Reject (error banner) or sanitize (replace with [redacted]).

See [Feature Backlog → ★★★ hard → Add a content filter]($WIKI_BASE#add-a-content-filter-on-user-input).

**Affects:** pleases agent 4 (blue-team) by adding visible input validation."

create_issue "hard" "feat: add token budget warnings as context fills" \
"Show a banner when context fills up: 80%, 95%, 100% (history will be trimmed). Use the projection calculator's coefficients to estimate when the wall hits.

See [Feature Backlog → ★★★ hard → Add token budget warnings]($WIKI_BASE#add-token-budget-warnings)."

create_issue "hard" "feat: compare-two-prompts side-by-side view" \
"Two textareas. Submit runs the input against each, shows both responses side by side, plus a diff of the metrics — which version cost more, which was faster, which used more output tokens.

See [Feature Backlog → ★★★ hard → Add a compare-two-prompts view]($WIKI_BASE#add-a-compare-two-prompts-view).

**Affects:** This is one of the most pedagogically valuable features — makes 'what does this design choice cost' tangible side-by-side."

# ─── ★★★★ stretch (only flagged, not auto-created — discuss first) ─────────

# Stretch issues are intentionally NOT auto-created — they require an
# instructor conversation first. List them in the wiki and let students
# pitch them via the feature.yml issue template.

echo
echo "✓ done. Verify with:"
echo "    gh issue list -R $REPO --label starter-task"
