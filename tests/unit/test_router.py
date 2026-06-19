import pytest

from finops_core.router import classify


@pytest.mark.parametrize("question,intent", [
    ("Am I over budget?", "anomaly"),
    ("any cost anomalies in the last week?", "anomaly"),
    ("will I exceed my budget this month?", "anomaly"),
    ("there's a weird spike in spending", "anomaly"),
    ("how can I reduce my AWS bill?", "optimize"),
    ("find me savings", "optimize"),
    ("show rightsizing recommendations", "optimize"),
    ("any idle resources I can clean up?", "optimize"),
    ("what are my top services by cost?", "cost"),
    ("break down EC2 by usage type", "cost"),
    ("what's my month-to-date spend?", "cost"),
    ("forecast for this month", "cost"),
])
def test_classify(question, intent):
    assert classify(question) == intent


def test_anomaly_beats_optimize_when_budget_mentioned():
    # "reduce" (optimize) + "budget" (anomaly) -> anomaly wins (checked first)
    assert classify("how do I reduce my budget overruns") == "anomaly"
