"""Numerical-accuracy harness: assert the agent's tool-layer figures match a direct,
independent Cost Explorer query. Run live via `finops accuracy` (or the gated pytest).
"""
from __future__ import annotations

from typing import Optional

from finops_core.config import Config
from finops_core.cost.dates import resolve_period
from finops_core.cost.explorer import CostExplorer

_TOLERANCE = 0.01  # dollars


def reconcile(session=None, cfg: Optional[Config] = None, period: str = "3m") -> dict:
    """Compare the by-service total (tool layer) against a raw, ungrouped GetCostAndUsage total
    for the same period — an independent check that our normalization preserves the numbers."""
    cfg = cfg or Config.load()
    if session is None:
        from finops_core.aws.session import build_session
        session = build_session(cfg)
    ce = CostExplorer(session, cfg)
    start, end = resolve_period(period)

    by_service = ce.cost_by_service(start=start, end=end)

    raw = ce.client.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="MONTHLY", Metrics=["UnblendedCost"],
    )
    raw_total = round(sum(float(b["Total"]["UnblendedCost"]["Amount"])
                          for b in raw.get("ResultsByTime", [])), 6)

    delta = round(abs(by_service.total - raw_total), 6)
    return {
        "ok": delta <= _TOLERANCE,
        "period": [start, end],
        "by_service_total": by_service.total,
        "raw_ce_total": raw_total,
        "delta": delta,
        "tolerance": _TOLERANCE,
    }
