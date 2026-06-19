"""Normalized cost result dataclasses (one source of truth for UI + agent + CLI)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class CostGroup:
    """One slice of a grouped cost breakdown (e.g. a single service or usage type)."""
    key: str
    amount: float
    unit: str
    pct: float = 0.0


@dataclass
class PeriodAmount:
    start: str
    end: str
    amount: float
    unit: str


@dataclass
class CostBreakdown:
    """Cost grouped by one dimension over a period (powers cost-per-service + drill-down)."""
    group_by: str
    start: str
    end: str
    granularity: str
    metric: str
    currency: str
    total: float
    groups: list  # list[CostGroup]
    others: Optional[float] = None      # summed tail when top_n truncates
    estimated: bool = False             # any sub-period still estimated by AWS
    filters: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CostSummary:
    """Total cost for a period, split into sub-periods (for trends/sparklines)."""
    start: str
    end: str
    granularity: str
    metric: str
    currency: str
    total: float
    by_period: list  # list[PeriodAmount]
    estimated: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Forecast:
    start: str
    end: str
    metric: str
    granularity: str
    currency: str
    total: float
    by_period: list  # list[{start,end,mean,lower,upper}]
    prediction_interval_level: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DimensionValues:
    dimension: str
    start: str
    end: str
    values: list  # list[str]

    def to_dict(self) -> dict:
        return asdict(self)
