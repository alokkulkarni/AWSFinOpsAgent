import pytest

from finops_core.cost.dates import forecast_period, resolve_period


def test_explicit_start_end_passthrough():
    assert resolve_period(start="2026-01-01", end="2026-02-01") == ("2026-01-01", "2026-02-01")


def test_mtd_starts_on_first_of_month():
    start, end = resolve_period("mtd")
    assert start.endswith("-01")
    assert start <= end


def test_last_month_is_a_full_prior_month():
    start, end = resolve_period("last_month")
    assert start.endswith("-01") and end.endswith("-01")
    assert start < end


@pytest.mark.parametrize("preset", ["7d", "30d", "90d"])
def test_day_presets(preset):
    start, end = resolve_period(preset)
    assert start < end


def test_trailing_months_start_on_first():
    start, _ = resolve_period("6m")
    assert start.endswith("-01")


def test_unknown_preset_raises():
    with pytest.raises(ValueError):
        resolve_period("nonsense")


def test_forecast_period_is_in_the_future():
    start, end = forecast_period("eom")
    assert start < end
