"""Steering playbooks for the DevOps agents (versioned .md, loaded into system prompts)."""
from __future__ import annotations

from pathlib import Path

STEERING_DIR = Path(__file__).resolve().parent


def load_steering(name: str) -> str:
    path = STEERING_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"no steering file for {name!r} ({path})")
    return path.read_text()
