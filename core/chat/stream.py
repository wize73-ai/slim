"""Streaming chat completions wrapper.

Wraps the OpenAI client's streaming chat completion with three things the
metrics tab needs:

1. **Timing instrumentation** — calls ``t.mark("t2")`` right before sending
   bytes to guapo, ``t.mark("t3")`` on the first content chunk back (which
   means prefill is done), and ``t.mark("t4")`` after the stream ends.

2. **Output filtering** — every chunk passes through :class:`StreamFilter`,
   redacting any guapo identifiers that slip through the security preamble.
   Boundary-spanning patterns are caught via the sliding-window buffer.

3. **Structured error handling** — guapo unavailability surfaces as
   :class:`UpstreamUnavailable` rather than a raw httpx error, so the
   FastAPI exception handler can render a user-friendly banner without
   leaking implementation details.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from core.chat.client import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    make_client,
)
from core.chat.errors import UpstreamTimeout, UpstreamUnavailable
from core.chat.messages import LabelledMessages
from core.chat.security import StreamFilter

if TYPE_CHECKING:
    from core.timing import Instrument


async def stream_completion(
    messages: LabelledMessages,
    *,
    instrument: Instrument | None = None,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> AsyncIterator[str]:
    """Stream a chat completion from guapo, filtered and instrumented.

    Yields content tokens (strings) as they arrive from the model. Each
    yielded chunk has already been passed through the security output filter,
    so any guapo identifiers the model might leak are redacted before
    reaching the caller.

    Args:
        messages: The labelled messages constructed by
            :func:`core.chat.build_request`.
        instrument: Optional :class:`core.timing.Instrument`. If supplied,
            this function calls ``t.mark("t2")`` right before sending bytes
            to guapo, ``t.mark("t3")`` on receiving the first content chunk
            (= prefill done), and ``t.mark("t4")`` after the stream ends
            (= decode done).
        model: Override the default model id. Defaults to the value from
            the ``CHAT_MODEL`` environment variable.
        temperature: Override the default sampling temperature.
        max_tokens: Override the default max output tokens.

    Yields:
        String chunks of content from the assistant's response, filtered.

    Raises:
        UpstreamUnavailable: Guapo is unreachable or returning 5xx, or the
            stream was interrupted by a connection error.
        UpstreamTimeout: Guapo accepted the request but failed to respond
            within the configured timeout.
    """
    # Lazy imports so the module is importable without the openai package
    # for security-boundary tests that only use messages/security.
    import httpx  # noqa: PLC0415
    from openai import APIConnectionError, APIStatusError, APITimeoutError  # noqa: PLC0415

    client = make_client()
    output_filter = StreamFilter()

    if instrument is not None:
        instrument.mark("t2")

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages.to_openai_messages(),  # type: ignore[arg-type]
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except APITimeoutError as e:
        # APITimeoutError is a subclass of APIConnectionError; catch it first
        # so the timeout case maps to UpstreamTimeout rather than the generic
        # unavailable signal.
        raise UpstreamTimeout("inference server timed out") from e
    except (APIConnectionError, httpx.ConnectError) as e:
        raise UpstreamUnavailable("inference server unreachable") from e
    except APIStatusError as e:
        if 500 <= e.status_code < 600:  # noqa: PLR2004
            raise UpstreamUnavailable(
                f"inference server returned {e.status_code}"
            ) from e
        raise

    first_chunk = True
    try:
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if not delta:
                continue
            if first_chunk:
                if instrument is not None:
                    instrument.mark("t3")
                first_chunk = False
            filtered = output_filter.feed(delta)
            if filtered:
                yield filtered
    except (APIConnectionError, httpx.ConnectError) as e:
        raise UpstreamUnavailable("stream interrupted") from e
    finally:
        # Always emit the buffer's tail (with one final filter pass), even on
        # cancellation, so the client receives whatever was already produced.
        tail = output_filter.flush()
        if tail:
            yield tail
        if instrument is not None:
            instrument.mark("t4")
