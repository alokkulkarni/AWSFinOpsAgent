"""Anomaly + budget tools for the Strands agent (and served over MCP)."""
from __future__ import annotations

from typing import Optional

from finops_core.anomaly.engine import AnomalyEngine
from finops_core.config import Config
from finops_core.cost.explorer import CostExplorer


def build_anomaly_tools(session=None, cfg: Optional[Config] = None,
                        eng: Optional[AnomalyEngine] = None, ce: Optional[CostExplorer] = None):
    from strands import tool

    eng = eng or AnomalyEngine(session, cfg)
    ce = ce or CostExplorer(session, cfg)

    @tool
    def get_cost_anomalies(period: str = "30d") -> dict:
        """Detected AWS cost anomalies for a period (default last 30 days), ranked by $ impact.
        Includes root causes and a note if no anomaly monitors are configured."""
        return eng.anomalies(period=period).to_dict()

    @tool
    def get_budgets_status() -> dict:
        """All AWS Budgets with actual + forecasted spend vs limit, and breach flags."""
        return eng.budgets().to_dict()

    @tool
    def get_forecast_vs_budget(metric: str = "UnblendedCost") -> dict:
        """Compare the end-of-month cost forecast against configured budgets (breach risk)."""
        forecast = ce.forecast(horizon="eom", metric=metric).to_dict()
        budgets = eng.budgets().to_dict()
        at_risk = [b for b in budgets["budgets"] if b.get("forecast_breach")]
        return {"forecast_eom": forecast["total"], "currency": forecast["currency"],
                "budgets": budgets["budgets"], "forecast_breaches": at_risk, "notes": budgets["notes"]}

    return [get_cost_anomalies, get_budgets_status, get_forecast_vs_budget]
