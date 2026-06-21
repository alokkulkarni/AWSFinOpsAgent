"""Review findings schema — a deterministic, citable finding and the per-resource review result."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

SEVERITY = ["critical", "high", "medium", "low", "info"]
_RANK = {s: i for i, s in enumerate(SEVERITY)}

# Categories a finding can fall under (Well-Architected-ish lenses).
CATEGORY = ["security", "reliability", "performance", "cost", "sizing", "config", "code"]


@dataclass
class Finding:
    rule_id: str           # stable id, e.g. "lambda.runtime.deprecated"
    title: str
    severity: str          # one of SEVERITY
    current: str           # observed value/state
    recommended: str       # best-practice target
    rationale: str         # why — per AWS best practice
    category: str = "config"
    doc_url: str = ""      # AWS documentation link (grounding)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ServiceReview:
    service: str
    resource_id: str
    region: Optional[str] = None
    summary: dict = field(default_factory=dict)    # observed config/sizing snapshot
    metrics: dict = field(default_factory=dict)     # CloudWatch metric snapshot
    findings: list = field(default_factory=list)    # list[Finding]
    notes: list = field(default_factory=list)       # graceful degradation / coverage notes

    def sorted_findings(self) -> list:
        return sorted(self.findings, key=lambda f: (_RANK.get(f.severity, 99), f.rule_id))

    def severity_counts(self) -> dict:
        out: dict = {}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def to_dict(self, limit: Optional[int] = None) -> dict:
        fs = self.sorted_findings()
        return {
            "service": self.service,
            "resource_id": self.resource_id,
            "region": self.region,
            "summary": self.summary,
            "metrics": self.metrics,
            "finding_count": len(self.findings),
            "by_severity": self.severity_counts(),
            "findings": [f.to_dict() for f in (fs[:limit] if limit else fs)],
            "notes": self.notes,
        }
