"""FinOps digest: the Workflow DAG.

The independent data tasks (cost-by-service, trend, forecast, anomalies, budgets, optimization)
run in parallel, then synthesize into a report. All numbers are deterministic (tool layer); an
optional short narrative uses the cheap `digest` model. Renders to Markdown / JSON / HTML.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

from finops_core.anomaly.engine import AnomalyEngine
from finops_core.config import Config
from finops_core.cost.explorer import CostExplorer
from finops_core.optimize.engine import Optimizer


def _money(x, cur="USD") -> str:
    return f"${x:,.2f}" if cur == "USD" else f"{cur} {x:,.2f}"


def gather(cfg: Optional[Config] = None, session=None) -> dict:
    """Run the independent digest tasks in parallel; return the raw section results."""
    cfg = cfg or Config.load()
    ce = CostExplorer(session, cfg)
    eng = AnomalyEngine(session, cfg)
    opt = Optimizer(session, cfg)

    tasks = {
        "mtd": lambda: ce.summary(period="mtd").to_dict(),
        "last_month": lambda: ce.summary(period="last_month").to_dict(),
        "by_service": lambda: ce.cost_by_service(period="mtd", top_n=5).to_dict(),
        "trend": lambda: ce.trend(months=6).to_dict(),
        "forecast": lambda: ce.forecast(horizon="eom").to_dict(),
        "anomalies": lambda: eng.anomalies(period="30d").to_dict(),
        "budgets": lambda: eng.budgets().to_dict(),
        "optimization": lambda: opt.all_recommendations().to_dict(),
    }
    out: dict = {"errors": []}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {k: ex.submit(fn) for k, fn in tasks.items()}
        for k, f in futures.items():
            try:
                out[k] = f.result()
            except Exception as e:  # one section failing shouldn't kill the digest
                out[k] = None
                out["errors"].append(f"{k}: {e}")
    return out


def _delta_pct(mtd: dict, last: dict) -> Optional[float]:
    lt = (last or {}).get("total") or 0
    return round(100 * ((mtd or {}).get("total", 0) - lt) / lt, 1) if lt else None


def render_markdown(data: dict, generated_at: str) -> str:
    cur = (data.get("mtd") or {}).get("currency", "USD")
    mtd = (data.get("mtd") or {}).get("total", 0)
    last = (data.get("last_month") or {}).get("total", 0)
    fc = (data.get("forecast") or {}).get("total")
    delta = _delta_pct(data.get("mtd") or {}, data.get("last_month") or {})
    lines = [f"# AWS FinOps Digest", f"_generated {generated_at}_", ""]
    lines += ["## Spend",
              f"- Month-to-date: **{_money(mtd, cur)}**"
              + (f" ({delta:+}% vs last month {_money(last, cur)})" if delta is not None else ""),
              f"- Forecast (EOM): **{_money(fc, cur)}**" if fc is not None else "", ""]

    bs = data.get("by_service") or {}
    if bs.get("groups"):
        lines.append("## Top services (MTD)")
        for g in bs["groups"]:
            lines.append(f"- {g['key']}: {_money(g['amount'], cur)} ({g['pct']}%)")
        lines.append("")

    an = data.get("anomalies") or {}
    lines.append("## Anomalies (30d)")
    if an.get("anomalies"):
        lines.append(f"- {an['count']} detected, total impact {_money(an['total_impact'], cur)}")
        for a in an["anomalies"][:3]:
            lines.append(f"  - {a['start'][:10]} {a['dimension']}: {_money(a['total_impact'], cur)}")
    else:
        lines.append("- none" + (f" ({an['notes'][0]})" if an.get("notes") else ""))
    lines.append("")

    bu = data.get("budgets") or {}
    lines.append("## Budgets")
    if bu.get("budgets"):
        for b in bu["budgets"]:
            flag = " ⚠️ OVER" if b["breached"] else (" ⚠️ forecast breach" if b["forecast_breach"] else "")
            lines.append(f"- {b['name']}: {_money(b['actual'], cur)} / {_money(b['limit'], cur)} "
                         f"({b['pct_used']}% used){flag}")
    else:
        lines.append("- none configured")
    lines.append("")

    op = data.get("optimization") or {}
    lines.append("## Top savings")
    if op.get("recommendations"):
        lines.append(f"- Potential: **{_money(op['total_monthly_savings'], cur)}/mo**")
        for r in op["recommendations"][:5]:
            lines.append(f"  - {_money(r['monthly_savings'], cur)}/mo — {r['title']} [{r['source']}]")
    else:
        lines.append("- no actionable recommendations from enrolled sources")
        for n in (op.get("notes") or [])[:3]:
            lines.append(f"  - note: {n}")
    if data.get("errors"):
        lines += ["", "## Notes"] + [f"- {e}" for e in data["errors"]]
    return "\n".join(line for line in lines if line is not None)


def render_html(markdown_text: str) -> str:
    body = markdown_text.replace("&", "&amp;").replace("<", "&lt;")
    return f"<!doctype html><meta charset=utf-8><title>AWS FinOps Digest</title><pre>{body}</pre>"


def narrative(data: dict, cfg: Config) -> Optional[str]:
    """One short paragraph from the cheap digest model (optional; numbers stay deterministic)."""
    try:
        from strands import Agent

        from finops_core.models.router import ModelRouter
        agent = Agent(
            model=ModelRouter(cfg).for_role("digest"),
            system_prompt="You write a 2-3 sentence executive summary of an AWS cost digest. "
                          "Do not invent numbers; only summarize what is given.",
            callback_handler=None,
        )
        import json
        return str(agent("Summarize this FinOps digest data:\n" + json.dumps(data)[:6000])).strip()
    except Exception:
        return None


def build_digest(cfg: Optional[Config] = None, session=None, fmt: str = "md",
                 with_narrative: bool = False, generated_at: Optional[str] = None) -> str:
    cfg = cfg or Config.load()
    data = gather(cfg, session)
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if fmt == "json":
        import json
        payload = {"generated_at": stamp, **data}
        if with_narrative:
            payload["narrative"] = narrative(data, cfg)
        return json.dumps(payload, indent=2)

    md = render_markdown(data, stamp)
    if with_narrative:
        n = narrative(data, cfg)
        if n:
            md = md.replace("\n\n", f"\n\n## Summary\n{n}\n\n", 1)
    return render_html(md) if fmt == "html" else md
