from finops_core.workflow.digest import _delta_pct, render_html, render_markdown

SAMPLE = {
    "mtd": {"total": 172.60, "currency": "USD"},
    "last_month": {"total": 56.10, "currency": "USD"},
    "forecast": {"total": 213.87, "currency": "USD"},
    "by_service": {"groups": [{"key": "Amazon Registrar", "amount": 71.0, "pct": 41.1}], "currency": "USD"},
    "anomalies": {"count": 1, "total_impact": 85.43,
                  "anomalies": [{"start": "2026-06-08", "dimension": "CodeBuild", "total_impact": 85.43}],
                  "notes": []},
    "budgets": {"budgets": [{"name": "My Monthly Cost Budget", "actual": 173.26, "limit": 10.0,
                            "pct_used": 1732.6, "breached": True, "forecast_breach": True}]},
    "optimization": {"total_monthly_savings": 0.0, "recommendations": [],
                     "notes": ["compute-optimizer: OptInRequired"]},
    "errors": [],
}


def test_delta_pct():
    assert _delta_pct({"total": 172.6}, {"total": 56.1}) == round(100 * (172.6 - 56.1) / 56.1, 1)
    assert _delta_pct({"total": 10}, {"total": 0}) is None


def test_render_markdown_sections():
    md = render_markdown(SAMPLE, "2026-06-19 12:00 UTC")
    assert "# AWS FinOps Digest" in md
    assert "Month-to-date: **$172.60**" in md
    assert "Forecast (EOM): **$213.87**" in md
    assert "Amazon Registrar" in md
    assert "CodeBuild" in md
    assert "OVER" in md                                   # budget breached flag
    assert "no actionable recommendations" in md          # optimization empty


def test_render_html_wraps_markdown():
    html = render_html(render_markdown(SAMPLE, "x"))
    assert html.startswith("<!doctype html>") and "<pre>" in html
