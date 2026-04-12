"""Locked baseline and mentor system prompts for the wize73 chatbot.

Students can LAYER their own system prompt via ``app/system_prompts/``
and their own persona via ``app/personas/``, but the locked baseline
and mentor prompts here always run as the foundation. The security
preamble from ``core.chat.security`` runs before everything.

Composition order for the main chatbot:

    <security_preamble from core.chat>
    <baseline from this module>
    <student system prompt from app/system_prompts/>
    <persona from app/personas/>

Composition for the mentor chatbot on /guide:

    <security_preamble from core.chat>
    <mentor from this module>
    (no student overlay — the mentor prompt is fully locked)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent
_BASELINE_PATH = _PROMPTS_DIR / "baseline.md"
_MENTOR_PATH = _PROMPTS_DIR / "mentor.md"


@lru_cache(maxsize=1)
def load_baseline() -> str:
    """Read the baseline system prompt from disk, cached."""
    return _BASELINE_PATH.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def load_mentor() -> str:
    """Read the mentor system prompt from disk, cached."""
    return _MENTOR_PATH.read_text(encoding="utf-8").strip()


__all__ = ["load_baseline", "load_mentor"]
