import pytest

from finops_core.steering import list_steering, load_steering


def test_load_cost_steering():
    text = load_steering("cost")
    assert "Cost-Analysis specialist" in text


def test_all_specialist_roles_present():
    available = set(list_steering())
    for name in ("orchestrator", "cost", "optimization", "anomaly"):
        assert name in available
        assert load_steering(name).strip()


def test_missing_steering_raises():
    with pytest.raises(FileNotFoundError):
        load_steering("nope-not-a-role")
