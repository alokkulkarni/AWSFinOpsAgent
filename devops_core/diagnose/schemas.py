"""Diagnosis schema — root-cause hypotheses with evidence and posture-shaped fixes."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

CONFIDENCE = ["high", "medium", "low"]
_RANK = {c: i for i, c in enumerate(CONFIDENCE)}


@dataclass
class Hypothesis:
    cause: str                 # root-cause hypothesis
    confidence: str            # high | medium | low
    evidence: list             # signal strings supporting it
    fix: str                   # advisory fix (what to do, in words)
    fix_command: str = ""      # concrete CLI/IaC to apply (artifacts/guarded only)
    category: str = "reliability"
    doc_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Diagnosis:
    service: str
    resource_id: str
    region: Optional[str] = None
    mode: str = "advisory"
    signals: dict = field(default_factory=dict)     # {config, alarms, log_errors, recent_changes}
    hypotheses: list = field(default_factory=list)   # list[Hypothesis]
    notes: list = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not self.hypotheses

    def sorted_hypotheses(self) -> list:
        return sorted(self.hypotheses, key=lambda h: _RANK.get(h.confidence, 9))

    def to_dict(self) -> dict:
        from finops_core.modes import can_apply_actions, can_generate_artifacts
        show_cmd = can_generate_artifacts(self.mode)        # artifacts + guarded_write
        needs_confirm = can_apply_actions(self.mode)        # guarded_write only
        hyps = []
        for h in self.sorted_hypotheses():
            d = h.to_dict()
            if not show_cmd:
                d.pop("fix_command", None)                  # advisory: no apply artifact
            elif needs_confirm and d.get("fix_command"):
                d["apply"] = "guarded_write: requires explicit human confirmation; NOT auto-applied"
            hyps.append(d)
        return {
            "service": self.service,
            "resource_id": self.resource_id,
            "region": self.region,
            "mode": self.mode,
            "healthy": self.healthy,
            "signals": self.signals,
            "hypotheses": hyps,
            "notes": self.notes,
        }
