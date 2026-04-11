"""Locked baseline system prompt for the wize73 chatbot.

Students can LAYER their own system prompt via ``app/system_prompts/``
and their own persona via ``app/personas/``, but the locked baseline
here always runs before those layers. The order of composition is:

    <security_preamble from core.chat>
    <baseline from this module>
    <student system prompt from app/system_prompts/>
    <persona from app/personas/>

The security preamble instructs the model never to leak guapo's URL /
IPs / model identifiers. The baseline sets the default tone, response
length, and posture of the assistant. Both are CODEOWNERS-protected.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_BASELINE_PATH = Path(__file__).resolve().parent / "baseline.md"


@lru_cache(maxsize=1)
def load_baseline() -> str:
    """Read the baseline system prompt from disk, cached.

    The file is read once per process and cached in memory. Restart the
    app to pick up changes — same pattern as other locked config.
    """
    return _BASELINE_PATH.read_text(encoding="utf-8").strip()


__all__ = ["load_baseline"]
