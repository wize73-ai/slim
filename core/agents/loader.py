"""Loader for agent prompt templates and rule data files.

The prompt files (markdown) and rule files (YAML) live in
``core/agents/prompts/``. They are CODEOWNERS-protected so students
can read them — and learn what each agent is checking — but cannot
edit them. This loader provides typed access to each file.

Loading is lazy and cached on first access. The cache is keyed by file
path, so swapping a file requires a Python process restart (which
happens on every PR-agent CI job anyway).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

# Resolve the prompts directory relative to this file. Works from any
# CWD, which matters because PR agents run from various working dirs.
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@cache
def load_text(name: str) -> str:
    """Read a markdown prompt template from the prompts directory.

    Args:
        name: File name including extension, e.g.
            ``"secrets_review_prompt.md"``.

    Returns:
        The full text contents.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


@cache
def load_yaml(name: str) -> Any:  # noqa: ANN401 — YAML loads heterogeneous shapes
    """Load a YAML rule/data file from the prompts directory.

    Args:
        name: File name including extension, e.g. ``"red_team_probes.yaml"``.

    Returns:
        The parsed YAML structure (typically dict or list of dicts).

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
    """
    # Lazy import so this module is testable without PyYAML for code-only tests.
    import yaml

    path = PROMPTS_DIR / name
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_red_team_probes() -> list[dict[str, str]]:
    """Load the 12 pre-written adversarial probes for agent 3.

    Each probe is a dict with at least ``id``, ``name``, ``category``,
    and ``prompt`` keys. See ``red_team_probes.yaml`` for the schema.
    """
    data = load_yaml("red_team_probes.yaml")
    return list(data.get("probes", []))


def load_classroom_safety_rules() -> dict[str, Any]:
    """Load the tunable classroom safety strictness configuration."""
    return load_yaml("classroom_safety_rules.yaml")  # type: ignore[no-any-return]


def load_lint_explanations() -> dict[str, str]:
    """Load the educational ruff-code → explanation lookup for agent 2."""
    return load_yaml("lint_explanations.yaml")  # type: ignore[no-any-return]


def load_discipline_explanations() -> dict[str, str]:
    """Load the educational hygiene-rule → explanation lookup for agent 6."""
    return load_yaml("discipline_explanations.yaml")  # type: ignore[no-any-return]


def load_judge_templates() -> dict[str, object]:
    """Load the shared judge prompt templates with verdict sentinel format."""
    return load_yaml("judge_templates.yaml")  # type: ignore[no-any-return]
