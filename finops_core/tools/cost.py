"""Cost-analysis tools exposed to the Strands agent. Each wraps a CostExplorer method and
returns a JSON-serializable dict. The LLM never sees the AWS session (captured in closure)."""
from __future__ import annotations

from typing import Optional

from finops_core.aws.org import OrgResolver
from finops_core.config import Config
from finops_core.cost.explorer import CostExplorer


def build_cost_tools(session=None, cfg: Optional[Config] = None, ce: Optional[CostExplorer] = None):
    """Return a list of @tool-decorated callables bound to one CostExplorer."""
    from strands import tool  # lazy import: only needed when wiring the agent

    ce = ce or CostExplorer(session, cfg)
    org = OrgResolver(session, cfg)

    @tool
    def get_cost_summary(period: str = "mtd", granularity: str = "MONTHLY",
                         metric: str = "UnblendedCost") -> dict:
        """Total AWS cost for a period, split into sub-periods.
        period: mtd | last_month | ytd | <N>d (e.g. 30d) | <N>m (e.g. 6m).
        granularity: MONTHLY or DAILY. metric: UnblendedCost | AmortizedCost | NetAmortizedCost."""
        return ce.summary(period=period, granularity=granularity, metric=metric).to_dict()

    @tool
    def get_cost_by_service(period: str = "mtd", top_n: int = 10,
                            granularity: str = "MONTHLY", metric: str = "UnblendedCost") -> dict:
        """Ranked cost per AWS service for a period — the cost-per-service view.
        Returns groups sorted high→low with each group's % of total; the tail beyond top_n
        is summarized in `others`."""
        return ce.cost_by_service(period=period, granularity=granularity,
                                  metric=metric, top_n=top_n).to_dict()

    @tool
    def get_cost_by_account(period: str = "mtd", top_n: int = 20,
                            metric: str = "UnblendedCost") -> dict:
        """Cost per linked account (AWS Organizations / consolidated billing), with account
        names. Run from the management (payer) account; otherwise returns the single account."""
        b = ce.cost_by_account(period=period, metric=metric, top_n=top_n).to_dict()
        try:
            return org.enrich_breakdown(b)
        except Exception:
            return b

    @tool
    def list_accounts() -> dict:
        """List the AWS accounts in scope (id -> name). Uses Organizations when run from the
        management account; otherwise returns the single current account."""
        return org.list_accounts()

    @tool
    def drill_down(group_by: str, filters: Optional[dict] = None, period: str = "mtd",
                   metric: str = "UnblendedCost", top_n: int = 15) -> dict:
        """Double-click into cost: group spend by `group_by` AFTER applying `filters`.

        group_by: SERVICE | USAGE_TYPE | OPERATION | REGION | LINKED_ACCOUNT | INSTANCE_TYPE |
                  PURCHASE_TYPE | RECORD_TYPE, or TAG:<key> / COST_CATEGORY:<name>.
        filters: narrow the scope first, e.g.
                 {"SERVICE": "Amazon Elastic Compute Cloud - Compute"} then group_by=USAGE_TYPE,
                 then add {"USAGE_TYPE": "..."} and group_by=REGION, and so on.
        Use list_dimension_values to discover exact filter values."""
        return ce.drill_down(group_by, filters or {}, period=period,
                             metric=metric, top_n=top_n).to_dict()

    @tool
    def get_cost_trend(months: int = 6, metric: str = "UnblendedCost") -> dict:
        """Monthly total cost over the last N months (for trends and month-over-month movers)."""
        return ce.trend(months=months, metric=metric).to_dict()

    @tool
    def get_cost_forecast(horizon: str = "eom", metric: str = "UnblendedCost",
                          granularity: str = "MONTHLY", prediction_interval: int = 80) -> dict:
        """Forecast future AWS cost with a confidence band.
        horizon: eom (end of current month) | <N>d | <N>m."""
        return ce.forecast(horizon=horizon, metric=metric, granularity=granularity,
                           pi_level=prediction_interval).to_dict()

    @tool
    def list_dimension_values(dimension: str, period: str = "mtd") -> dict:
        """List valid values for a Cost Explorer dimension (SERVICE, REGION, USAGE_TYPE,
        OPERATION, LINKED_ACCOUNT, INSTANCE_TYPE, ...). Use to find exact `filters` values."""
        return ce.dimension_values(dimension, period=period).to_dict()

    return [
        get_cost_summary, get_cost_by_service, get_cost_by_account, drill_down,
        get_cost_trend, get_cost_forecast, list_dimension_values, list_accounts,
    ]
