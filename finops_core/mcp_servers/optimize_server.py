"""Optimize-tools MCP server (distributed tool tier).

Serves the optimization recommendation tools over MCP Streamable HTTP.
Run: python -m finops_core.mcp_servers.optimize_server  (or: finops serve optimize-tools)
Env: FINOPS_MCP_HOST (0.0.0.0 in containers), FINOPS_OPTIMIZE_MCP_PORT (8082). Serves at /mcp.
"""
from __future__ import annotations

import os
from dataclasses import asdict

from mcp.server import FastMCP

from finops_core.config import Config
from finops_core.optimize.engine import Optimizer

_cfg = Config.load()
_opt = Optimizer(cfg=_cfg)

mcp = FastMCP(
    "finops-optimize-tools",
    host=os.getenv("FINOPS_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("FINOPS_OPTIMIZE_MCP_PORT", "8082")),
)


def _serialize(recs_notes) -> dict:
    recs, notes = recs_notes
    return {
        "count": len(recs),
        "total_monthly_savings": round(sum(r.monthly_savings for r in recs), 2),
        "recommendations": [asdict(r) for r in recs],
        "notes": notes,
    }


@mcp.tool(description="All AWS savings recommendations, deduped + ranked by est. monthly savings "
                     "(rightsizing, Compute Optimizer, Savings Plans/RI, Cost Optimization Hub, Trusted Advisor).")
def get_optimization_summary() -> dict:
    return _opt.all_recommendations().to_dict()


@mcp.tool(description="Cost Explorer EC2 rightsizing recommendations (modify or terminate idle).")
def get_rightsizing_recommendations(service: str = "AmazonEC2") -> dict:
    return _serialize(_opt.rightsizing(service=service))


@mcp.tool(description="Compute Optimizer recommendations for EC2/EBS/Lambda (needs enrollment).")
def get_compute_optimizer_recommendations() -> dict:
    return _serialize(_opt.compute_optimizer())


@mcp.tool(description="Compute Savings Plan purchase recommendation.")
def get_savings_plans_recommendations(term: str = "ONE_YEAR", payment: str = "NO_UPFRONT") -> dict:
    return _serialize(_opt.savings_plans(term=term, payment=payment))


@mcp.tool(description="Reserved Instance purchase recommendations for a service.")
def get_reservation_recommendations(service: str = "Amazon Elastic Compute Cloud - Compute") -> dict:
    return _serialize(_opt.reservations(service=service))


@mcp.tool(description="Cost Optimization Hub unified recommendations (needs enrollment).")
def get_cost_optimization_hub_recommendations() -> dict:
    return _serialize(_opt.cost_optimization_hub())


@mcp.tool(description="Trusted Advisor cost checks (needs Business/Enterprise Support).")
def get_trusted_advisor_cost_checks() -> dict:
    return _serialize(_opt.trusted_advisor_cost())


def main() -> None:
    from finops_core.mcp_servers._runtime import run_mcp
    run_mcp(mcp, "optimize-tools")


if __name__ == "__main__":
    main()
