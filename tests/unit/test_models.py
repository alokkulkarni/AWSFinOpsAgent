from finops_core.config import Config
from finops_core.models.router import ModelRouter


def test_temperature_default_is_zero():
    assert Config.load().llm.temperature == 0.0


def test_max_tokens_default():
    # explicit maxTokens avoids over-reserving Bedrock quota (ThrottlingException)
    assert Config.load().llm.max_tokens == 2048


def test_prompt_caching_enabled_by_default():
    llm = Config.load().llm
    assert llm.cache_prompt is True and llm.cache_tools is True


def test_max_tokens_env_override(monkeypatch):
    monkeypatch.setenv("FINOPS_LLM_MAX_TOKENS", "512")
    assert Config.load().llm.max_tokens == 512


def test_guardrail_disabled_by_default():
    assert Config.load().llm.guardrail_id is None


def test_guardrail_env_override(monkeypatch):
    monkeypatch.setenv("FINOPS_GUARDRAIL_ID", "abc123")
    monkeypatch.setenv("FINOPS_GUARDRAIL_VERSION", "2")
    llm = Config.load().llm
    assert llm.guardrail_id == "abc123" and llm.guardrail_version == "2"


def test_temperature_env_override(monkeypatch):
    monkeypatch.setenv("FINOPS_LLM_TEMPERATURE", "0.4")
    assert Config.load().llm.temperature == 0.4


def test_model_id_resolution_and_fallback():
    r = ModelRouter(Config.load())
    assert "nova" in r.model_id("digest")
    assert r.model_id("orchestrator")  # configured, non-empty
    # an unknown role falls back to the orchestrator model
    assert r.model_id("does-not-exist") == r.model_id("orchestrator")
