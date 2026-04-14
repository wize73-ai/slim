"""Structured exceptions for the core.chat module.

These exceptions are raised by the chat module and surface as user-facing
banners (via the FastAPI exception handler) and as records in the metrics
ring buffer. They never contain guapo's URL or any other identifier from
the obfuscation list — error messages are scrubbed at the boundary.
"""

from __future__ import annotations


class ChatError(Exception):
    """Base for all core.chat errors. Catch this to handle anything we raise."""


class UpstreamUnavailable(ChatError):
    """The inference server is unreachable or returning 5xx.

    Surfaced as a friendly 'service is restarting, try again in a moment'
    banner. The original exception is chained for logs but the public message
    never names the inference host.
    """


class UpstreamTimeout(ChatError):
    """The inference server accepted the request but did not respond in time."""


class InvalidRequest(ChatError):
    """Client supplied a malformed request — bad slot, oversized history, etc."""


class ContextWindowExceeded(ChatError):
    """Composed messages exceeded the model's context window.

    Carries the over-budget token count so the metrics tab can show the user
    where they exceeded.
    """

    def __init__(self, requested_tokens: int, max_tokens: int) -> None:
        """Record the requested vs. maximum context size."""
        self.requested_tokens = requested_tokens
        self.max_tokens = max_tokens
        super().__init__(f"requested {requested_tokens} tokens, model max is {max_tokens}")


class FilterBlocked(ChatError):
    """Output filter caught a guapo identifier in the response stream.

    This is a serious event — it means the model leaked something the security
    preamble told it not to. The filter still redacts the leak inline and the
    chat continues; this exception is raised in the metrics path so the
    instructor ops dashboard can flag it as a high-severity event.
    """

    def __init__(self, redaction_count: int) -> None:
        """Record how many redactions the filter performed."""
        self.redaction_count = redaction_count
        super().__init__(f"output filter redacted {redaction_count} pattern matches")
