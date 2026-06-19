"""Deterministic data layer for the dashboard.

Every number shown in the UI comes from here — i.e. straight from the CostExplorer tool
layer (the same functions the agent calls), never from an LLM. This is the "deterministic
number pass-through": tables and drill-downs are exact by construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from finops_core.aws.session import build_session
from finops_core.config import Config
from finops_core.cost.explorer import CostExplorer
from finops_core.schemas.cost import CostBreakdown

# Order in which "double-click" descends. SERVICE is the root view.
DRILL_ORDER = ["SERVICE", "USAGE_TYPE", "OPERATION", "REGION", "LINKED_ACCOUNT"]


@dataclass
class DrillLevel:
    dimension: str
    value: str


def breadcrumb_to_query(stack: list[DrillLevel]) -> tuple[Optional[str], dict]:
    """Given the chosen drill levels, return (next group_by dimension, filters).

    stack=[]                              -> ("SERVICE", {})
    stack=[SERVICE=Amazon EC2]            -> ("USAGE_TYPE", {"SERVICE": "Amazon EC2"})
    stack=[SERVICE=.., USAGE_TYPE=..]     -> ("OPERATION", {...})
    fully drilled                         -> (None, {...})
    """
    filters = {lvl.dimension: lvl.value for lvl in stack}
    chosen = {lvl.dimension for lvl in stack}
    next_dim = next((d for d in DRILL_ORDER if d not in chosen), None)
    return next_dim, filters


class CostDashboardData:
    """Thin, cached wrapper over CostExplorer used by the Streamlit app and (later) the API."""

    def __init__(self, cfg: Optional[Config] = None, ce: Optional[CostExplorer] = None):
        self.cfg = cfg or Config.load()
        self.ce = ce or CostExplorer(build_session(self.cfg), self.cfg)

    def breakdown(
        self,
        stack: list[DrillLevel],
        *,
        period: str = "mtd",
        metric: str = "UnblendedCost",
        granularity: str = "MONTHLY",
        top_n: int = 12,
    ) -> Optional[CostBreakdown]:
        """Cost grouped at the current drill level (None when fully drilled in)."""
        group_by, filters = breadcrumb_to_query(stack)
        if group_by is None:
            return None
        return self.ce.grouped_cost(
            group_by, period=period, granularity=granularity,
            metric=metric, filters=filters, top_n=top_n,
        )

    def kpis(self, *, metric: str = "UnblendedCost") -> dict:
        mtd = self.ce.summary(period="mtd", metric=metric)
        last = self.ce.summary(period="last_month", metric=metric)
        svc = self.ce.cost_by_service(period="mtd", metric=metric, top_n=1)
        try:
            forecast = self.ce.forecast(horizon="eom", metric=metric)
            forecast_total = forecast.total
        except Exception:
            forecast_total = None
        top = svc.groups[0] if svc.groups else None
        delta = None
        if last.total:
            delta = round(100.0 * (mtd.total - last.total) / last.total, 1)
        return {
            "currency": mtd.currency,
            "mtd_total": mtd.total,
            "last_month_total": last.total,
            "delta_pct_vs_last_month": delta,
            "forecast_eom": forecast_total,
            "top_service": (top.key if top else None),
            "top_service_amount": (top.amount if top else None),
            "estimated": mtd.estimated,
        }

    def trend(self, *, months: int = 6, metric: str = "UnblendedCost"):
        return self.ce.trend(months=months, metric=metric)
