"""OpenAI-compatible client factory.

Reads ``OPENAI_BASE_URL`` and ``OPENAI_API_KEY`` from environment at runtime.
The URL is **never** hardcoded in source — it lives only as an environment
variable on the deploy box, so guapo's address never appears in the
student-facing repo.

Same env-var contract as the standard OpenAI Python client, so students who
import this module are learning the same pattern they would use against
cloud OpenAI, Anthropic, Gemini, or any compatible provider.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from openai import AsyncOpenAI

# The model identifier on guapo. Configurable via env so the same code works
# against any OpenAI-compatible server. Default matches guapo's frozen
# INTERFACE.md.
DEFAULT_MODEL: Final[str] = os.environ.get("CHAT_MODEL", "/models/phi-4-mini")

# Default sampling parameters. Students can override per-call via the
# ``stream_completion()`` keyword arguments.
DEFAULT_TEMPERATURE: Final[float] = float(os.environ.get("CHAT_TEMPERATURE", "0.7"))
DEFAULT_MAX_TOKENS: Final[int] = int(os.environ.get("CHAT_MAX_TOKENS", "1024"))


def make_client() -> AsyncOpenAI:
    """Build an :class:`openai.AsyncOpenAI` client from environment variables.

    Reads:
        ``OPENAI_BASE_URL``: Required. Set on the deploy box only — never in
            source code, never in git, never in templates.
        ``OPENAI_API_KEY``: Optional, defaults to ``"sk-local"``. Guapo does
            not enforce auth currently, but the OpenAI client requires
            *some* value, so a placeholder is provided.

    Returns:
        An ``AsyncOpenAI`` client configured to talk to whatever server
        ``OPENAI_BASE_URL`` points to.

    Raises:
        KeyError: If ``OPENAI_BASE_URL`` is not set in the environment.
    """
    # Lazy import so this module can be imported in test contexts that don't
    # have the openai package installed (e.g., security-only test runs).
    from openai import AsyncOpenAI  # noqa: PLC0415

    base_url = os.environ["OPENAI_BASE_URL"]
    api_key = os.environ.get("OPENAI_API_KEY", "sk-local")
    return AsyncOpenAI(base_url=base_url, api_key=api_key)
