"""Deterministic anomaly + budget engine (Cost Anomaly Detection + AWS Budgets).

Degrades to notes when a source is empty/unavailable (e.g. no anomaly monitors configured).
"""
from __future__ import annotations

from typing import Optional

from finops_core.aws.session import client
from finops_core.config import Config
from finops_core.cost.dates import resolve_period
from finops_core.schemas.anomaly import Anomaly, AnomalyReport, Budget, BudgetReport


def _money(x) -> float:
    if isinstance(x, dict):
        x = x.get("Amount") or x.get("amount") or 0
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


class AnomalyEngine:
    def __init__(self, session=None, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self.session = session

    def _client(self, service: str, region: Optional[str] = None):
        if self.session is None:
            from finops_core.aws.session import build_session
            self.session = build_session(self.cfg)
        return client(self.session, service, region=region)

    def _account_id(self) -> Optional[str]:
        try:
            return self._client("sts").get_caller_identity()["Account"]
        except Exception:
            return None

    # ---- anomalies ----------------------------------------------------
    def anomalies(self, period: str = "30d", start: str | None = None, end: str | None = None) -> AnomalyReport:
        start, end = resolve_period(period, start, end)
        anomalies, monitors, notes = [], [], []
        ce = self._client("ce", self.cfg.aws.ce_region)
        try:
            for m in ce.get_anomaly_monitors().get("AnomalyMonitors", []):
                monitors.append(m.get("MonitorName") or m.get("MonitorArn", ""))
        except Exception as e:
            notes.append(f"anomaly-monitors: {e}")
        try:
            token = None
            while True:
                kw = {"DateInterval": {"StartDate": start, "EndDate": end}}
                if token:
                    kw["NextPageToken"] = token
                resp = ce.get_anomalies(**kw)
                for a in resp.get("Anomalies", []):
                    impact = a.get("Impact", {})
                    causes = []
                    for rc in a.get("RootCauses", []):
                        causes.append(" / ".join(filter(None, [
                            rc.get("Service"), rc.get("Region"), rc.get("UsageType")])))
                    anomalies.append(Anomaly(
                        id=a.get("AnomalyId", ""),
                        start=a.get("AnomalyStartDate", ""), end=a.get("AnomalyEndDate"),
                        dimension=(a.get("DimensionValue") or "—"),
                        total_impact=round(_money(impact.get("TotalImpact")), 2),
                        max_impact=round(_money(impact.get("MaxImpact")), 2),
                        score=round(_money(a.get("AnomalyScore", {}).get("MaxScore")), 4),
                        monitor=a.get("MonitorArn"), root_causes=[c for c in causes if c],
                    ))
                token = resp.get("NextPageToken")
                if not token:
                    break
            if not monitors:
                notes.append("No anomaly monitors configured — create one to enable detection "
                             "(ce:CreateAnomalyMonitor).")
        except Exception as e:
            notes.append(f"anomalies: {e}")
        anomalies.sort(key=lambda x: x.total_impact, reverse=True)
        total = round(sum(a.total_impact for a in anomalies), 2)
        return AnomalyReport(start, end, len(anomalies), total, "USD", anomalies, monitors, notes)

    # ---- budgets ------------------------------------------------------
    def budgets(self) -> BudgetReport:
        budgets, notes = [], []
        account = self._account_id()
        if not account:
            return BudgetReport(0, "USD", [], ["could not resolve account id for Budgets"])
        try:
            bud = self._client("budgets", "us-east-1")
            token = None
            while True:
                kw = {"AccountId": account, "MaxResults": 100}
                if token:
                    kw["NextToken"] = token
                resp = bud.describe_budgets(**kw)
                for b in resp.get("Budgets", []):
                    limit = _money(b.get("BudgetLimit"))
                    spend = b.get("CalculatedSpend", {})
                    actual = _money(spend.get("ActualSpend"))
                    forecast = _money(spend.get("ForecastedSpend")) if spend.get("ForecastedSpend") else None
                    pct = round(100 * actual / limit, 1) if limit else None
                    fpct = round(100 * forecast / limit, 1) if (limit and forecast is not None) else None
                    budgets.append(Budget(
                        name=b.get("BudgetName", ""), limit=round(limit, 2), actual=round(actual, 2),
                        forecasted=(round(forecast, 2) if forecast is not None else None),
                        currency=(b.get("BudgetLimit", {}) or {}).get("Unit", "USD"),
                        time_unit=b.get("TimeUnit", ""), budget_type=b.get("BudgetType", ""),
                        pct_used=pct, forecast_pct=fpct,
                        breached=bool(limit and actual > limit),
                        forecast_breach=bool(limit and forecast is not None and forecast > limit),
                    ))
                token = resp.get("NextToken")
                if not token:
                    break
            if not budgets:
                notes.append("No budgets configured — create one to track spend vs target "
                             "(budgets:CreateBudget).")
        except Exception as e:
            notes.append(f"budgets: {e}")
        return BudgetReport(len(budgets), "USD", budgets, notes)
