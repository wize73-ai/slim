"""LabelledMessages: the data structure for token-flow decomposition.

:func:`build_request` constructs a :class:`LabelledMessages` from the
labelled slots (system, persona, examples, history, user). Each slot is
tracked separately so the metrics tab's pyramid chart can show students
how many tokens each design decision is costing them per turn.

The slots define the public API students extend as they implement
features — adding a persona means populating the ``persona`` slot, adding
history means populating the ``history`` slot, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from core.chat.security import compose_system_prompt

if TYPE_CHECKING:
    import tiktoken

# Tokenizer for local approximate token counts. Phi-4-mini uses a tokenizer
# in the GPT-4o family; ``o200k_base`` is the closest match available in
# tiktoken. Counts are slightly approximate but the relative ordering of
# slot sizes (which slot costs more) is what matters for teaching, and that
# is preserved.
#
# Local tokenization is intentional — hammering guapo's tokenize endpoint
# (if it even exists) would compete with student chat traffic on a
# single-worker server. Local is fast and free.
_ENCODING_NAME: Final[str] = "o200k_base"

# Lazy global; populated on first use to keep import-time light.
_encoding: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    """Lazily load the tiktoken encoding on first call."""
    global _encoding  # noqa: PLW0603 — module-level cache is intentional
    if _encoding is None:
        import tiktoken

        _encoding = tiktoken.get_encoding(_ENCODING_NAME)
    return _encoding


def count_tokens(text: str) -> int:
    """Count tokens in text using the local approximation tokenizer.

    Args:
        text: Any string of text to tokenize.

    Returns:
        The integer token count according to ``o200k_base``. Empty strings
        return zero.
    """
    if not text:
        return 0
    return len(_get_encoding().encode(text))


@dataclass(frozen=True, slots=True)
class FewShotExample:
    """A single ``(user, assistant)`` pair from a few-shot example block."""

    user: str
    assistant: str


@dataclass(frozen=True, slots=True)
class HistoryMessage:
    """A single previously-exchanged message in the conversation history.

    The ``role`` is the OpenAI-style role string (``"user"`` or ``"assistant"``),
    not a structured enum, to keep the data shape simple for student YAML/JSON.
    """

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class LabelledMessages:
    """Composed messages with per-slot token accounting.

    Each labelled slot tracks its own token count so the metrics tab can
    decompose the per-turn input into "where did the tokens come from" —
    the central insight of the bidirectional framing.

    Use :meth:`to_openai_messages` to flatten into the list-of-dicts format
    that the OpenAI client expects when sending to guapo.

    The ``persona_tokens`` field reports the persona text's token count
    independently, even though those tokens are also embedded in
    ``system_text`` (and therefore counted in ``system_tokens``). This is so
    the metrics tab can show "your persona costs N tokens per turn" as a
    separate line item — students need to see persona cost in isolation to
    optimize it.
    """

    system_text: str
    persona_text: str
    examples: tuple[FewShotExample, ...]
    history: tuple[HistoryMessage, ...]
    user_text: str

    system_tokens: int
    persona_tokens: int
    examples_tokens: int
    history_tokens: int
    user_tokens: int

    @property
    def total_input_tokens(self) -> int:
        """Sum of all labelled slot tokens that contribute to the input.

        Note that ``persona_tokens`` is *not* added because the persona
        contribution is already inside ``system_tokens``. The total represents
        the actual cost of one turn's input on guapo.
        """
        return self.system_tokens + self.examples_tokens + self.history_tokens + self.user_tokens

    def to_openai_messages(self) -> list[dict[str, str]]:
        """Flatten into the OpenAI client messages format.

        The ``system_text`` already contains preamble + baseline + student
        system + persona, so the persona is not a separate message.

        Few-shot examples are interleaved as user/assistant pairs *before*
        the conversation history, which itself precedes the current user
        message. This is the order most chat completion APIs expect.

        Returns:
            A list of ``{"role": ..., "content": ...}`` dicts ready to pass
            to ``client.chat.completions.create(messages=...)``.
        """
        msgs: list[dict[str, str]] = [{"role": "system", "content": self.system_text}]
        for ex in self.examples:
            msgs.append({"role": "user", "content": ex.user})
            msgs.append({"role": "assistant", "content": ex.assistant})
        msgs.extend({"role": h.role, "content": h.content} for h in self.history)
        msgs.append({"role": "user", "content": self.user_text})
        return msgs


def build_request(
    *,
    baseline: str,
    user: str,
    student_system: str = "",
    persona: str = "",
    examples: tuple[FewShotExample, ...] = (),
    history: tuple[HistoryMessage, ...] = (),
) -> LabelledMessages:
    """Construct a :class:`LabelledMessages` from the labelled input slots.

    All slots except ``baseline`` and ``user`` are optional. The dumb v1
    chatbot supplies only those two; students extend the chatbot by
    populating the other slots as they implement features.

    Keyword-only to prevent positional confusion between similar string
    arguments — ``user`` and ``persona`` and ``baseline`` are easy to mix up.

    Args:
        baseline: The locked baseline system prompt from ``core.prompts``.
            Required.
        user: The current user message. Required.
        student_system: Optional student-supplied system text overlay from
            ``app/system_prompts/``.
        persona: Optional persona block (text) from ``app/personas/``.
        examples: Optional tuple of :class:`FewShotExample` pairs from
            ``app/examples/``.
        history: Optional tuple of prior :class:`HistoryMessage` items
            from the session.

    Returns:
        A :class:`LabelledMessages` instance with composed text and per-slot
        token counts ready for the metrics tab.
    """
    system_text = compose_system_prompt(
        baseline=baseline,
        student_system=student_system,
        persona=persona,
    )

    # Token accounting per slot. Persona contribution is counted separately
    # for the metrics tab even though those tokens are already embedded in
    # system_text.
    persona_tokens = count_tokens(persona)
    system_tokens = count_tokens(system_text)
    examples_tokens = sum(count_tokens(ex.user) + count_tokens(ex.assistant) for ex in examples)
    history_tokens = sum(count_tokens(h.content) for h in history)
    user_tokens = count_tokens(user)

    return LabelledMessages(
        system_text=system_text,
        persona_text=persona,
        examples=examples,
        history=history,
        user_text=user,
        system_tokens=system_tokens,
        persona_tokens=persona_tokens,
        examples_tokens=examples_tokens,
        history_tokens=history_tokens,
        user_tokens=user_tokens,
    )
