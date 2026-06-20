"""Steering files — versioned Markdown playbooks that define each agent's behavior.

Keeping the prompts as .md (not Python strings) means they can be reviewed, diffed, and edited
like docs. `agents/prompts.py` loads these into the agent system prompts.
"""
from __future__ import annotations

from pathlib import Path

STEERING_DIR = Path(__file__).resolve().parent


def load_steering(name: str) -> str:
    """Return the steering playbook for `name` (e.g. 'cost'). Raises if missing."""
    path = STEERING_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"no steering file for {name!r} ({path})")
    return path.read_text()


def list_steering() -> list[str]:
    return sorted(p.stem for p in STEERING_DIR.glob("*.md"))
