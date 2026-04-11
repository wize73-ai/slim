{# Student-editable system prompt overlay.

   The dumb v1 chatbot deliberately has an empty overlay — the locked
   baseline in core/prompts/baseline.md is all there is. Add your own
   system prompt text here to shape how the model behaves beyond the
   baseline.

   Feature backlog starter issue: "Write a better default system prompt"
   — pick it up as one of your first PRs. Ideas:
     - Set a consistent tone across personas
     - Tell the model to refuse off-topic questions
     - Ask the model to be more or less concise by default
     - Give it a consistent fallback for "I don't know"

   Note that your system prompt is paid on every turn forever. The
   pyramid chart on /metrics will show you exactly how many tokens it
   costs — optimize accordingly.
#}
