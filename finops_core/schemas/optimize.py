"""Normalized optimization result types (one shape across all recommendation sources)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Recommendation:
    source: str            # rightsizing | compute-optimizer | savings-plans | reservations |
                           # cost-optimization-hub | trusted-advisor
    title: str
    category: str          # rightsize | idle | commitment | cleanup | other
    monthly_savings: float
    currency: str = "USD"
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    account: Optional[str] = None
    region: Optional[str] = None
    current: Optional[str] = None
    recommended: Optional[str] = None
    effort: str = "medium"     # low | medium | high
    risk: str = "medium"       # low | medium | high
    rationale: str = ""
    action: Optional[str] = None

    def key(self) -> tuple:
        """Dedup key: same resource + action collapses (keep highest savings)."""
        return (self.resource_id or self.title, self.category, self.action or "")


@dataclass
class OptimizationReport:
    total_monthly_savings: float
    currency: str
    count: int
    by_source: dict
    recommendations: list           # list[Recommendation]
    notes: list = field(default_factory=list)   # e.g. "Compute Optimizer not enrolled"

    def to_dict(self) -> dict:
        return asdict(self)
