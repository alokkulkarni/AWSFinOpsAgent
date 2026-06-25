"""Anomaly-tools MCP server (distributed tool tier): Cost Anomaly Detection + Budgets.

Run: finops serve anomaly-tools
Env: FINOPS_MCP_HOST (0.0.0.0), FINOPS_ANOMALY_MCP_PORT (8083). Serves at /mcp.
"""
from __future__ import annotations

import os

from mcp.server import FastMCP

from finops_core.anomaly.engine import AnomalyEngine
from finops_core.aws.session import build_session
from finops_core.config import Config
from finops_core.cost.explorer import CostExplorer

_cfg = Config.load()
_session = build_session(_cfg)
_eng = AnomalyEngine(_session, _cfg)
_ce = CostExplorer(_session, _cfg)

mcp = FastMCP(
    "finops-anomaly-tools",
    host=os.getenv("FINOPS_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("FINOPS_ANOMALY_MCP_PORT", "8083")),
)


@mcp.tool(description="Detected AWS cost anomalies for a period (default 30d), ranked by $ impact, "
                     "with root causes; notes if no anomaly monitors are configured.")
def get_cost_anomalies(period: str = "30d") -> dict:
    return _eng.anomalies(period=period).to_dict()


@mcp.tool(description="All AWS Budgets with actual + forecasted spend vs limit and breach flags.")
def get_budgets_status() -> dict:
    return _eng.budgets().to_dict()


@mcp.tool(description="Compare end-of-month cost forecast against configured budgets (breach risk).")
def get_forecast_vs_budget(metric: str = "UnblendedCost") -> dict:
    forecast = _ce.forecast(horizon="eom", metric=metric).to_dict()
    budgets = _eng.budgets().to_dict()
    at_risk = [b for b in budgets["budgets"] if b.get("forecast_breach")]
    return {"forecast_eom": forecast["total"], "currency": forecast["currency"],
            "budgets": budgets["budgets"], "forecast_breaches": at_risk, "notes": budgets["notes"]}


def main() -> None:
    from finops_core.mcp_servers._runtime import run_mcp
    run_mcp(mcp, "anomaly-tools")


if __name__ == "__main__":
    main()
