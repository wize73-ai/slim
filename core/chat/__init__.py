"""OpenAI-compatible chat client wrapper for guapo.

This is the locked surface between student-editable ``app/`` code and the
inference server on guapo. It provides:

* :func:`build_request` — construct labelled messages from the slots
  (system, persona, examples, history, user) so the metrics tab can
  decompose per-turn token cost.
* :func:`stream_completion` — stream a response from guapo with timing
  instrumentation, output filtering, and structured error handling.
* :data:`SECURITY_PREAMBLE` — non-overridable system prompt prepend that
  forbids leaking URLs/IPs/model IDs/hostnames; automatically applied by
  :func:`compose_system_prompt`.
* :class:`StreamFilter` — sliding-window regex redactor that catches any
  guapo identifier the model leaks despite the preamble.
* Structured exceptions (:class:`UpstreamUnavailable`,
  :class:`UpstreamTimeout`, :class:`ContextWindowExceeded`,
  :class:`FilterBlocked`, :class:`InvalidRequest`) for graceful error
  handling in the chat handler.

Students consume this module's public API but cannot edit it — the entire
``core/`` package is CODEOWNERS-protected so the security boundary and the
measurement integrity stay constant across PRs.
"""

from core.chat.client import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    make_client,
)
from core.chat.errors import (
    ChatError,
    ContextWindowExceeded,
    FilterBlocked,
    InvalidRequest,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from core.chat.messages import (
    FewShotExample,
    HistoryMessage,
    LabelledMessages,
    build_request,
    count_tokens,
)
from core.chat.security import (
    SECURITY_PREAMBLE,
    StreamFilter,
    compose_system_prompt,
)
from core.chat.stream import stream_completion

__all__ = [
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_MODEL",
    "DEFAULT_TEMPERATURE",
    "SECURITY_PREAMBLE",
    "ChatError",
    "ContextWindowExceeded",
    "FewShotExample",
    "FilterBlocked",
    "HistoryMessage",
    "InvalidRequest",
    "LabelledMessages",
    "StreamFilter",
    "UpstreamTimeout",
    "UpstreamUnavailable",
    "build_request",
    "compose_system_prompt",
    "count_tokens",
    "make_client",
    "stream_completion",
]
