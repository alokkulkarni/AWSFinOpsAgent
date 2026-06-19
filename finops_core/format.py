"""Terminal rendering for cost results (CLI fast path)."""
from __future__ import annotations

from finops_core.schemas.cost import CostBreakdown, CostSummary, Forecast
from finops_core.schemas.optimize import OptimizationReport, Recommendation


def money(amount: float, unit: str = "USD") -> str:
    prefix = "$" if unit.upper() == "USD" else f"{unit} "
    return f"{prefix}{amount:,.2f}"


def print_breakdown(b: CostBreakdown) -> None:
    flt = f"  filters={b.filters}" if b.filters else ""
    est = "  (includes estimated data)" if b.estimated else ""
    print(f"\n{b.group_by} — [{b.start} .. {b.end})  metric={b.metric}{flt}{est}")
    if not b.groups:
        print("  (no cost data for this period/scope)")
        return
    width = min(max((len(g.key) for g in b.groups), default=8), 60)
    for g in b.groups:
        print(f"  {g.key[:60]:<{width}}  {money(g.amount, b.currency):>14}  {g.pct:5.1f}%")
    if b.others is not None:
        print(f"  {'(others)':<{width}}  {money(b.others, b.currency):>14}")
    print(f"  {'-' * width}  {'-' * 14}")
    print(f"  {'TOTAL':<{width}}  {money(b.total, b.currency):>14}")


def print_summary(s: CostSummary) -> None:
    est = "  (includes estimated data)" if s.estimated else ""
    print(f"\nTotal — [{s.start} .. {s.end})  metric={s.metric}{est}")
    for p in s.by_period:
        print(f"  {p.start} .. {p.end}  {money(p.amount, p.unit):>14}")
    print(f"  {'-' * 24}  {'-' * 14}")
    print(f"  {'TOTAL':<24}  {money(s.total, s.currency):>14}")


def print_recommendations(recs: list, notes: list) -> None:
    if not recs:
        print("  (no recommendations from this source)")
    for r in recs:
        loc = " ".join(x for x in (r.region, r.resource_id) if x)
        print(f"  {money(r.monthly_savings, r.currency):>11}/mo  [{r.source}/{r.risk} risk]  {r.title}"
              + (f"  · {loc}" if loc else ""))
        if r.current or r.recommended:
            print(f"               {r.current or '?'}  →  {r.recommended or '?'}")
    for n in notes:
        print(f"  ! {n}")


def print_optimization(report: OptimizationReport) -> None:
    print(f"\nPotential savings: {money(report.total_monthly_savings, report.currency)}/mo "
          f"across {report.count} recommendation(s)")
    if report.by_source:
        print("  by source: " + ", ".join(f"{k}={v}" for k, v in report.by_source.items()))
    print()
    print_recommendations(report.recommendations, report.notes)


def print_forecast(f: Forecast) -> None:
    print(f"\nForecast — [{f.start} .. {f.end})  metric={f.metric}  PI={f.prediction_interval_level}%")
    for p in f.by_period:
        print(f"  {p['start']} .. {p['end']}  mean {money(p['mean'], f.currency):>12}"
              f"   [{money(p['lower'], f.currency)} .. {money(p['upper'], f.currency)}]")
    print(f"  TOTAL mean {money(f.total, f.currency)}")
