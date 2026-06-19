"""Optimization tools exposed to the Strands agent (and served over MCP). Each returns a
JSON-serializable dict; the AWS session is captured in the closure."""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from finops_core.config import Config
from finops_core.optimize.engine import Optimizer


def _serialize(recs_notes) -> dict:
    recs, notes = recs_notes
    return {
        "count": len(recs),
        "total_monthly_savings": round(sum(r.monthly_savings for r in recs), 2),
        "recommendations": [asdict(r) for r in recs],
        "notes": notes,
    }


def build_optimize_tools(session=None, cfg: Optional[Config] = None, opt: Optional[Optimizer] = None):
    from strands import tool

    opt = opt or Optimizer(session, cfg)

    @tool
    def get_optimization_summary() -> dict:
        """All AWS cost-savings recommendations, deduped and ranked by estimated monthly
        savings (rightsizing + Compute Optimizer + Savings Plans/RI + Cost Optimization Hub +
        Trusted Advisor). Returns total potential monthly savings, per-source counts, the
        ranked list, and notes about any source that is unavailable/not enrolled."""
        return opt.all_recommendations().to_dict()

    @tool
    def get_rightsizing_recommendations(service: str = "AmazonEC2") -> dict:
        """Cost Explorer EC2 rightsizing recommendations (modify or terminate idle)."""
        return _serialize(opt.rightsizing(service=service))

    @tool
    def get_compute_optimizer_recommendations() -> dict:
        """AWS Compute Optimizer recommendations for EC2, EBS, and Lambda (needs enrollment)."""
        return _serialize(opt.compute_optimizer())

    @tool
    def get_savings_plans_recommendations(term: str = "ONE_YEAR", payment: str = "NO_UPFRONT") -> dict:
        """Compute Savings Plan purchase recommendation (estimated monthly savings)."""
        return _serialize(opt.savings_plans(term=term, payment=payment))

    @tool
    def get_reservation_recommendations(service: str = "Amazon Elastic Compute Cloud - Compute") -> dict:
        """Reserved Instance purchase recommendations for a service."""
        return _serialize(opt.reservations(service=service))

    @tool
    def get_cost_optimization_hub_recommendations() -> dict:
        """AWS Cost Optimization Hub unified recommendations (needs enrollment)."""
        return _serialize(opt.cost_optimization_hub())

    @tool
    def get_trusted_advisor_cost_checks() -> dict:
        """Trusted Advisor cost-optimization checks (needs Business/Enterprise Support)."""
        return _serialize(opt.trusted_advisor_cost())

    return [
        get_optimization_summary, get_rightsizing_recommendations,
        get_compute_optimizer_recommendations, get_savings_plans_recommendations,
        get_reservation_recommendations, get_cost_optimization_hub_recommendations,
        get_trusted_advisor_cost_checks,
    ]
