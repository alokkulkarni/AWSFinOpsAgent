"""Cost-tools MCP server (distributed tool tier).

Exposes the Cost Explorer tools over MCP Streamable HTTP so any agent (or the API gateway)
can consume them remotely. Wraps the same in-process CostExplorer — one source of truth.

Run: python -m finops_core.mcp_servers.cost_server
Env: FINOPS_MCP_HOST (0.0.0.0 in containers), FINOPS_MCP_PORT (8081). Serves at /mcp.

Connector mode: users pass their own AWS credentials via X-Aws-* request headers.
Server-side mode (local dev / Docker stack): credentials come from ~/.aws or env vars.
"""
from __future__ import annotations

import os

from mcp.server import FastMCP
from mcp.server.fastmcp import Context

from finops_core.aws.org import OrgResolver
from finops_core.config import Config
from finops_core.cost.explorer import CostExplorer
from finops_core.mcp_servers.connector_auth import session_from_context

_cfg = Config.load()

mcp = FastMCP(
    "finops-cost-tools",
    host=os.getenv("FINOPS_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("FINOPS_MCP_PORT", "8081")),
)


@mcp.tool(description="Total AWS cost for a period (mtd|last_month|ytd|30d|6m), split by sub-period.")
def get_cost_summary(period: str = "mtd", granularity: str = "MONTHLY",
                     metric: str = "UnblendedCost", ctx: Context = None) -> dict:
    session = session_from_context(ctx, _cfg)
    return CostExplorer(session, _cfg).summary(period=period, granularity=granularity, metric=metric).to_dict()


@mcp.tool(description="Ranked cost per AWS service for a period; groups with % of total, tail in 'others'.")
def get_cost_by_service(period: str = "mtd", top_n: int = 10, granularity: str = "MONTHLY",
                        metric: str = "UnblendedCost", ctx: Context = None) -> dict:
    session = session_from_context(ctx, _cfg)
    return CostExplorer(session, _cfg).cost_by_service(period=period, granularity=granularity,
                                                        metric=metric, top_n=top_n).to_dict()


@mcp.tool(description="Cost per linked account (AWS Organizations / consolidated billing), with names.")
def get_cost_by_account(period: str = "mtd", top_n: int = 20, metric: str = "UnblendedCost",
                        ctx: Context = None) -> dict:
    session = session_from_context(ctx, _cfg)
    b = CostExplorer(session, _cfg).cost_by_account(period=period, metric=metric, top_n=top_n).to_dict()
    try:
        return OrgResolver(session, _cfg).enrich_breakdown(b)
    except Exception:
        return b


@mcp.tool(description="List AWS accounts in scope (id -> name); Organizations when run from the payer.")
def list_accounts(ctx: Context = None) -> dict:
    session = session_from_context(ctx, _cfg)
    return OrgResolver(session, _cfg).list_accounts()


@mcp.tool(description=(
    "Double-click into cost: group by group_by (SERVICE|USAGE_TYPE|OPERATION|REGION|"
    "LINKED_ACCOUNT|INSTANCE_TYPE|TAG:<k>) AFTER applying filters (dict of dimension->value)."
))
def drill_down(group_by: str, filters: dict | None = None, period: str = "mtd",
               metric: str = "UnblendedCost", top_n: int = 15, ctx: Context = None) -> dict:
    session = session_from_context(ctx, _cfg)
    return CostExplorer(session, _cfg).drill_down(group_by, filters or {}, period=period,
                                                   metric=metric, top_n=top_n).to_dict()


@mcp.tool(description="Monthly total cost over the last N months (trends / month-over-month movers).")
def get_cost_trend(months: int = 6, metric: str = "UnblendedCost", ctx: Context = None) -> dict:
    session = session_from_context(ctx, _cfg)
    return CostExplorer(session, _cfg).trend(months=months, metric=metric).to_dict()


@mcp.tool(description="Forecast future AWS cost with a confidence band. horizon: eom|<N>d|<N>m.")
def get_cost_forecast(horizon: str = "eom", metric: str = "UnblendedCost",
                      granularity: str = "MONTHLY", prediction_interval: int = 80,
                      ctx: Context = None) -> dict:
    session = session_from_context(ctx, _cfg)
    return CostExplorer(session, _cfg).forecast(horizon=horizon, metric=metric, granularity=granularity,
                                                 pi_level=prediction_interval).to_dict()


@mcp.tool(description="List valid values for a Cost Explorer dimension (SERVICE, REGION, USAGE_TYPE, ...).")
def list_dimension_values(dimension: str, period: str = "mtd", ctx: Context = None) -> dict:
    session = session_from_context(ctx, _cfg)
    return CostExplorer(session, _cfg).dimension_values(dimension, period=period).to_dict()


def main() -> None:
    from finops_core.mcp_servers._runtime import run_mcp
    run_mcp(mcp, "cost-tools")


if __name__ == "__main__":
    main()
