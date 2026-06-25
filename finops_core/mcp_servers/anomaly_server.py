"""Anomaly-tools MCP server (distributed tool tier): Cost Anomaly Detection + Budgets.

Run: finops serve anomaly-tools
Env: FINOPS_MCP_HOST (0.0.0.0), FINOPS_ANOMALY_MCP_PORT (8083). Serves at /mcp.

Connector mode: users pass their own AWS credentials via X-Aws-* request headers.
Server-side mode (local dev / Docker stack): credentials come from ~/.aws or env vars.
"""
from __future__ import annotations

import os

from mcp.server import FastMCP
from mcp.server.fastmcp import Context

from finops_core.anomaly.engine import AnomalyEngine
from finops_core.config import Config
from finops_core.cost.explorer import CostExplorer
from finops_core.mcp_servers.connector_auth import session_from_context

_cfg = Config.load()

mcp = FastMCP(
    "finops-anomaly-tools",
    host=os.getenv("FINOPS_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("FINOPS_ANOMALY_MCP_PORT", "8083")),
)


@mcp.tool(description="Detected AWS cost anomalies for a period (default 30d), ranked by $ impact, "
                     "with root causes; notes if no anomaly monitors are configured.")
def get_cost_anomalies(period: str = "30d", ctx: Context = None) -> dict:
    session = session_from_context(ctx, _cfg)
    return AnomalyEngine(session, _cfg).anomalies(period=period).to_dict()


@mcp.tool(description="All AWS Budgets with actual + forecasted spend vs limit and breach flags.")
def get_budgets_status(ctx: Context = None) -> dict:
    session = session_from_context(ctx, _cfg)
    return AnomalyEngine(session, _cfg).budgets().to_dict()


@mcp.tool(description="Compare end-of-month cost forecast against configured budgets (breach risk).")
def get_forecast_vs_budget(metric: str = "UnblendedCost", ctx: Context = None) -> dict:
    session = session_from_context(ctx, _cfg)
    forecast = CostExplorer(session, _cfg).forecast(horizon="eom", metric=metric).to_dict()
    budgets = AnomalyEngine(session, _cfg).budgets().to_dict()
    at_risk = [b for b in budgets["budgets"] if b.get("forecast_breach")]
    return {"forecast_eom": forecast["total"], "currency": forecast["currency"],
            "budgets": budgets["budgets"], "forecast_breaches": at_risk, "notes": budgets["notes"]}


def main() -> None:
    from finops_core.mcp_servers._runtime import run_mcp
    run_mcp(mcp, "anomaly-tools")


if __name__ == "__main__":
    main()
