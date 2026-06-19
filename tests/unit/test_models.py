from finops_core.config import Config
from finops_core.models.router import ModelRouter


def test_temperature_default_is_zero():
    assert Config.load().llm.temperature == 0.0


def test_temperature_env_override(monkeypatch):
    monkeypatch.setenv("FINOPS_LLM_TEMPERATURE", "0.4")
    assert Config.load().llm.temperature == 0.4


def test_model_id_resolution_and_fallback():
    r = ModelRouter(Config.load())
    assert "nova" in r.model_id("digest")
    assert r.model_id("orchestrator")  # configured, non-empty
    # an unknown role falls back to the orchestrator model
    assert r.model_id("does-not-exist") == r.model_id("orchestrator")
