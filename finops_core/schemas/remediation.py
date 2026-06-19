"""Remediation result types (artifacts + guarded actions)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Artifact:
    """A generated, ready-to-run fix — never executed by the agent."""
    format: str               # terraform | cli | cloudformation
    filename: str
    content: str
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ActionSpec:
    """An allowlisted guarded-write action and what it would do (dry-run preview)."""
    action_id: str
    title: str
    risk: str                 # low | medium | high
    params: dict = field(default_factory=dict)
    preview: str = ""         # human-readable description of the effect
    confirmation_token: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ActionResult:
    action_id: str
    status: str               # applied | rejected | error
    detail: str
    audit_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)
