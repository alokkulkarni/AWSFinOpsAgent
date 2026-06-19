"""Deterministic Cost Explorer wrapper. Returns normalized dataclasses used by the UI
(fast path), the Strands tools (agent), and the CLI — one source of truth for numbers.

Cost Explorer must be called via us-east-1. The End date is exclusive.
"""
from __future__ import annotations

from typing import Optional

from finops_core.aws.cache import TTLCache
from finops_core.aws.session import client
from finops_core.config import Config
from finops_core.cost.dates import forecast_period, resolve_period
from finops_core.schemas.cost import (
    CostBreakdown,
    CostGroup,
    CostSummary,
    DimensionValues,
    Forecast,
    PeriodAmount,
)

# GetCostForecast uses SCREAMING_SNAKE metric names; GetCostAndUsage uses CamelCase.
_FORECAST_METRIC = {
    "UnblendedCost": "UNBLENDED_COST",
    "AmortizedCost": "AMORTIZED_COST",
    "NetAmortizedCost": "NET_AMORTIZED_COST",
    "NetUnblendedCost": "NET_UNBLENDED_COST",
    "BlendedCost": "BLENDED_COST",
}


def _round(x: float) -> float:
    return round(x, 6)


class CostExplorer:
    def __init__(
        self,
        session=None,
        cfg: Optional[Config] = None,
        ce_client=None,
        cache: Optional[TTLCache] = None,
    ):
        self.cfg = cfg or Config()
        # ce_client injectable for tests (botocore Stubber)
        self.client = ce_client or client(session, "ce", region=self.cfg.aws.ce_region)
        self.cache = cache if cache is not None else TTLCache(self.cfg.cache_ttl_seconds)

    # ---- helpers -------------------------------------------------------
    @staticmethod
    def _group_key(group_by: str) -> dict:
        """Map a group_by string to a Cost Explorer GroupBy entry.
        'SERVICE' -> dimension; 'TAG:Env' -> tag; 'COST_CATEGORY:Team' -> cost category."""
        if ":" in group_by:
            kind, key = group_by.split(":", 1)
            kind = kind.upper()
            if kind == "TAG":
                return {"Type": "TAG", "Key": key}
            if kind in ("COST_CATEGORY", "COSTCATEGORY"):
                return {"Type": "COST_CATEGORY", "Key": key}
        return {"Type": "DIMENSION", "Key": group_by.upper()}

    @staticmethod
    def _build_filter(filters: dict) -> Optional[dict]:
        """Build a Cost Explorer Filter (AND of dimensions/tags/cost-categories)."""
        if not filters:
            return None
        clauses = []
        for key, val in filters.items():
            values = val if isinstance(val, list) else [val]
            if key.startswith("TAG:"):
                clauses.append({"Tags": {"Key": key[4:], "Values": values}})
            elif key.startswith("COST_CATEGORY:"):
                clauses.append({"CostCategories": {"Key": key[14:], "Values": values}})
            else:
                clauses.append({"Dimensions": {"Key": key.upper(), "Values": values}})
        return clauses[0] if len(clauses) == 1 else {"And": clauses}

    def _get_cost_and_usage(self, *, start, end, granularity, metric, group_by=None, cost_filter=None):
        kwargs = {
            "TimePeriod": {"Start": start, "End": end},
            "Granularity": granularity,
            "Metrics": [metric],
        }
        if group_by:
            kwargs["GroupBy"] = group_by
        if cost_filter:
            kwargs["Filter"] = cost_filter
        results, token = [], None
        while True:
            if token:
                kwargs["NextPageToken"] = token
            resp = self.client.get_cost_and_usage(**kwargs)
            results.extend(resp.get("ResultsByTime", []))
            token = resp.get("NextPageToken")
            if not token:
                break
        return results

    # ---- grouped breakdowns (cost-per-X + drill-down) ------------------
    def grouped_cost(
        self,
        group_by: str,
        *,
        period: str = "mtd",
        start: str | None = None,
        end: str | None = None,
        granularity: str = "MONTHLY",
        metric: str = "UnblendedCost",
        filters: dict | None = None,
        top_n: int | None = None,
    ) -> CostBreakdown:
        start, end = resolve_period(period, start, end)
        gb = [self._group_key(group_by)]
        cost_filter = self._build_filter(filters or {})

        results = self.cache.get_or_compute(
            ("grouped", group_by, start, end, granularity, metric, repr(filters)),
            lambda: self._get_cost_and_usage(
                start=start, end=end, granularity=granularity, metric=metric,
                group_by=gb, cost_filter=cost_filter,
            ),
        )

        totals: dict[str, float] = {}
        unit, estimated = "USD", False
        for block in results:
            estimated = estimated or block.get("Estimated", False)
            for g in block.get("Groups", []):
                key = " / ".join(g.get("Keys", [])) or "(unattributed)"
                amt = g["Metrics"][metric]
                unit = amt.get("Unit", unit)
                totals[key] = totals.get(key, 0.0) + float(amt["Amount"])

        groups = sorted(
            (CostGroup(k, _round(v), unit) for k, v in totals.items()),
            key=lambda g: g.amount,
            reverse=True,
        )
        total = _round(sum(g.amount for g in groups))

        others = None
        if top_n and len(groups) > top_n:
            tail = groups[top_n:]
            others = _round(sum(g.amount for g in tail))
            groups = groups[:top_n]
        for g in groups:
            g.pct = round(100.0 * g.amount / total, 2) if total else 0.0

        return CostBreakdown(
            group_by=group_by, start=start, end=end, granularity=granularity, metric=metric,
            currency=unit, total=total, groups=groups, others=others, estimated=estimated,
            filters=filters or {},
        )

    def cost_by_service(self, **kw) -> CostBreakdown:
        return self.grouped_cost("SERVICE", **kw)

    def cost_by_account(self, **kw) -> CostBreakdown:
        return self.grouped_cost("LINKED_ACCOUNT", **kw)

    def cost_by_tag(self, tag_key: str, **kw) -> CostBreakdown:
        return self.grouped_cost(f"TAG:{tag_key}", **kw)

    def drill_down(self, group_by: str, filters: dict, **kw) -> CostBreakdown:
        """The 'double-click': group by `group_by` after applying `filters`."""
        return self.grouped_cost(group_by, filters=filters, **kw)

    # ---- totals / trend / forecast / dimensions ------------------------
    def summary(
        self,
        *,
        period: str = "mtd",
        start: str | None = None,
        end: str | None = None,
        granularity: str = "MONTHLY",
        metric: str = "UnblendedCost",
    ) -> CostSummary:
        start, end = resolve_period(period, start, end)
        results = self.cache.get_or_compute(
            ("summary", start, end, granularity, metric),
            lambda: self._get_cost_and_usage(
                start=start, end=end, granularity=granularity, metric=metric
            ),
        )
        by_period, total, unit, estimated = [], 0.0, "USD", False
        for block in results:
            amt = block["Total"][metric]
            unit = amt.get("Unit", unit)
            value = float(amt["Amount"])
            total += value
            estimated = estimated or block.get("Estimated", False)
            tp = block["TimePeriod"]
            by_period.append(PeriodAmount(tp["Start"], tp["End"], _round(value), unit))
        return CostSummary(start, end, granularity, metric, unit, _round(total), by_period, estimated)

    def trend(self, *, months: int = 6, metric: str = "UnblendedCost") -> CostSummary:
        start, end = resolve_period(f"{months}m")
        return self.summary(start=start, end=end, granularity="MONTHLY", metric=metric)

    def forecast(
        self,
        *,
        horizon: str = "eom",
        metric: str = "UnblendedCost",
        granularity: str = "MONTHLY",
        pi_level: int = 80,
    ) -> Forecast:
        start, end = forecast_period(horizon)
        resp = self.client.get_cost_forecast(
            TimePeriod={"Start": start, "End": end},
            Metric=_FORECAST_METRIC.get(metric, "UNBLENDED_COST"),
            Granularity=granularity,
            PredictionIntervalLevel=pi_level,
        )
        unit = resp["Total"].get("Unit", "USD")
        by_period = []
        for f in resp.get("ForecastResultsByTime", []):
            tp = f["TimePeriod"]
            mean = float(f["MeanValue"])
            by_period.append({
                "start": tp["Start"],
                "end": tp["End"],
                "mean": _round(mean),
                "lower": _round(float(f.get("PredictionIntervalLowerBound", mean))),
                "upper": _round(float(f.get("PredictionIntervalUpperBound", mean))),
            })
        return Forecast(
            start, end, metric, granularity, unit,
            _round(float(resp["Total"]["Amount"])), by_period, pi_level,
        )

    def dimension_values(
        self, dimension: str, *, period: str = "mtd", start: str | None = None, end: str | None = None
    ) -> DimensionValues:
        start, end = resolve_period(period, start, end)
        values, token = [], None
        while True:
            kwargs = {"TimePeriod": {"Start": start, "End": end}, "Dimension": dimension.upper()}
            if token:
                kwargs["NextPageToken"] = token
            resp = self.client.get_dimension_values(**kwargs)
            values.extend(v["Value"] for v in resp.get("DimensionValues", []))
            token = resp.get("NextPageToken")
            if not token:
                break
        return DimensionValues(dimension.upper(), start, end, values)
