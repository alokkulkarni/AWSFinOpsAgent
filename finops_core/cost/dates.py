"""Date-range helpers. Cost Explorer treats the End date as EXCLUSIVE."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

ISO = "%Y-%m-%d"


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def _add_months(first: date, months: int) -> date:
    """Shift a first-of-month date by `months` (may be negative)."""
    idx = (first.year * 12 + (first.month - 1)) + months
    return date(idx // 12, idx % 12 + 1, 1)


def resolve_period(
    period: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> tuple[str, str]:
    """Return (start, end) ISO dates; end is EXCLUSIVE.

    Explicit start+end win. Otherwise `period` presets:
      mtd | this_month, last_month, ytd, <N>d (e.g. 30d), <N>m (e.g. 6m, trailing months).
    """
    if start and end:
        return start, end
    today = _today()
    p = (period or "mtd").lower()

    if p in ("mtd", "month", "this_month"):
        return _first_of_month(today).strftime(ISO), today.strftime(ISO)
    if p in ("last_month", "lastmonth", "prev_month"):
        first_this = _first_of_month(today)
        return _add_months(first_this, -1).strftime(ISO), first_this.strftime(ISO)
    if p == "ytd":
        return date(today.year, 1, 1).strftime(ISO), today.strftime(ISO)
    if p.endswith("d") and p[:-1].isdigit():
        n = int(p[:-1])
        return (today - timedelta(days=n)).strftime(ISO), today.strftime(ISO)
    if p.endswith("m") and p[:-1].isdigit():
        n = max(1, int(p[:-1]))
        start_d = _add_months(_first_of_month(today), -(n - 1))
        return start_d.strftime(ISO), today.strftime(ISO)

    raise ValueError(f"unknown period preset: {period!r} (try mtd, last_month, 30d, 6m, ytd)")


def forecast_period(horizon: str = "eom") -> tuple[str, str]:
    """Future (start, end) for GetCostForecast; start = today (required to be >= today)."""
    today = _today()
    h = (horizon or "eom").lower()
    if h in ("eom", "month", "this_month"):
        return today.strftime(ISO), _add_months(_first_of_month(today), 1).strftime(ISO)
    if h.endswith("d") and h[:-1].isdigit():
        return today.strftime(ISO), (today + timedelta(days=int(h[:-1]))).strftime(ISO)
    if h.endswith("m") and h[:-1].isdigit():
        return today.strftime(ISO), _add_months(_first_of_month(today), int(h[:-1])).strftime(ISO)
    raise ValueError(f"unknown forecast horizon: {horizon!r} (try eom, 30d, 3m)")
