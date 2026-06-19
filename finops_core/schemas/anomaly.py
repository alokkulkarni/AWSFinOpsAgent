"""Normalized anomaly + budget result types."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Anomaly:
    id: str
    start: str
    end: Optional[str]
    dimension: str            # service the anomaly is attributed to
    total_impact: float       # $ over expected
    max_impact: float
    score: float
    currency: str = "USD"
    monitor: Optional[str] = None
    root_causes: list = field(default_factory=list)


@dataclass
class AnomalyReport:
    start: str
    end: str
    count: int
    total_impact: float
    currency: str
    anomalies: list           # list[Anomaly]
    monitors: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Budget:
    name: str
    limit: float
    actual: float
    forecasted: Optional[float]
    currency: str
    time_unit: str
    budget_type: str
    pct_used: Optional[float]
    forecast_pct: Optional[float]
    breached: bool
    forecast_breach: bool


@dataclass
class BudgetReport:
    count: int
    currency: str
    budgets: list             # list[Budget]
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
