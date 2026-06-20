import pytest

pytest.importorskip("pydantic")

from finops_core.schemas.answer import Figure, FinOpsAnswer  # noqa: E402


def test_finops_answer_validates_and_serializes():
    a = FinOpsAnswer(
        headline="Month-to-date spend is $172.60",
        period="mtd", metric="UnblendedCost",
        figures=[Figure(label="Amazon EC2", amount=71.0, unit="USD", pct=41.1)],
    )
    d = a.model_dump()
    assert d["headline"].startswith("Month-to-date")
    assert d["period"] == "mtd"
    assert d["figures"][0]["label"] == "Amazon EC2"
    assert d["figures"][0]["amount"] == 71.0


def test_figures_default_empty():
    a = FinOpsAnswer(headline="no cost data for this period")
    assert a.figures == []
    assert a.note is None
