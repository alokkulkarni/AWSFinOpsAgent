"""Prompt caching uses the non-deprecated Strands API (cache_config), not cache_prompt.
Guards against the `cache_prompt is deprecated` UserWarning regressing across both products."""
import warnings

import pytest

from finops_core.config import Config
from finops_core.models.router import ModelRouter

pytest.importorskip("strands")  # building a BedrockModel needs the agent extra


def _model(role="devops"):
    cfg = Config.load()
    return ModelRouter(cfg).for_role(role)


def test_caching_uses_cache_config_not_cache_prompt():
    cfg = _model().get_config()
    assert cfg.get("cache_config") is not None          # auto prompt caching, new API
    assert not cfg.get("cache_prompt")                  # deprecated knob not used
    assert cfg.get("cache_tools")                       # tool-definition caching still on


def test_building_model_emits_no_cache_prompt_deprecation():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _model()
    assert not [w for w in caught if "cache_prompt is deprecated" in str(w.message)]
