"""Shared test fixtures."""
import pytest


@pytest.fixture(autouse=True)
def _no_telemetry_export(monkeypatch):
    """Keep the suite hermetic: disable OTEL export so the entrypoint bootstraps (FastAPI startup,
    CLI ``main``, dashboard) are no-ops in tests and never push spans to pytest's captured streams.

    The telemetry unit tests build ``Config()`` directly (constructor, env-independent) or their own
    providers, so this doesn't affect them. ``reset_telemetry`` clears the idempotency cache so no
    global provider leaks across tests.
    """
    monkeypatch.setenv("FINOPS_TELEMETRY", "0")
    try:
        from finops_core.telemetry import reset_telemetry
        reset_telemetry()
        yield
        reset_telemetry()
    except Exception:
        yield
