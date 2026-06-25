"""Conversation management (context-rot fix): the SummarizingConversationManager builder and
the guarantee that every long-lived agent factory threads it ON by default — summarizing old
turns instead of dropping them — while ``summarize: false`` reverts to Strands' default."""
import importlib

import pytest

from finops_core.config import Config
from finops_core.conversation import build_conversation_manager


class _FakeRouter:
    def for_role(self, role):  # ModelRouter normally returns a (lazy) BedrockModel
        return object()


# --- config defaults / gating ---------------------------------------------
def test_summarize_on_by_default():
    cfg = Config()
    assert cfg.conversation.summarize is True
    assert cfg.conversation.preserve_recent == 10
    assert cfg.conversation.summary_ratio == 0.3
    assert cfg.conversation.proactive_threshold == 0.7


def test_env_disables_summarize(monkeypatch):
    monkeypatch.setenv("FINOPS_CONVERSATION_SUMMARIZE", "false")
    assert Config.load().conversation.summarize is False


# --- builder ---------------------------------------------------------------
def test_builder_returns_summarizing_manager_with_config():
    from strands.agent.conversation_manager import SummarizingConversationManager

    cm = build_conversation_manager(Config(), router=_FakeRouter())
    assert isinstance(cm, SummarizingConversationManager)
    assert cm.summary_ratio == 0.3
    assert cm.preserve_recent_messages == 10
    assert cm._compression_threshold == 0.7  # proactive: compress before overflow
    assert cm.summarization_system_prompt  # a tuned, non-empty prompt
    # Exact-number posture: the summary prompt must preserve figures, not estimate them.
    assert "exact" in cm.summarization_system_prompt.lower()


def test_builder_none_when_disabled():
    cfg = Config()
    cfg.conversation.summarize = False
    assert build_conversation_manager(cfg, router=_FakeRouter()) is None


def test_proactive_threshold_zero_means_reactive_only():
    cfg = Config()
    cfg.conversation.proactive_threshold = 0.0
    cm = build_conversation_manager(cfg, router=_FakeRouter())
    assert cm._compression_threshold is None  # reactive (on overflow) only


# --- factory threading (monkeypatched Agent → no Bedrock) ------------------
def _capture_agent(monkeypatch):
    captured = {}

    class FakeAgent:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr("strands.Agent", FakeAgent)
    return captured


@pytest.mark.parametrize(
    "factory_path,builder",
    [
        ("finops_core.agents.cost", "build_cost_agent"),
        ("finops_core.agents.optimize", "build_optimize_agent"),
        ("finops_core.agents.anomaly", "build_anomaly_agent"),
    ],
)
def test_finops_factories_thread_cm_by_default(monkeypatch, factory_path, builder):
    from strands.agent.conversation_manager import SummarizingConversationManager

    captured = _capture_agent(monkeypatch)
    build = getattr(importlib.import_module(factory_path), builder)
    build(router=_FakeRouter(), tools=[], cfg=Config())
    assert isinstance(captured["conversation_manager"], SummarizingConversationManager)


@pytest.mark.parametrize(
    "factory_path,builder",
    [
        ("finops_core.agents.cost", "build_cost_agent"),
        ("finops_core.agents.optimize", "build_optimize_agent"),
        ("finops_core.agents.anomaly", "build_anomaly_agent"),
    ],
)
def test_finops_factories_no_cm_when_off(monkeypatch, factory_path, builder):
    captured = _capture_agent(monkeypatch)
    build = getattr(importlib.import_module(factory_path), builder)
    build(router=_FakeRouter(), tools=[], cfg=Config(), conversation=False)
    assert "conversation_manager" not in captured


def test_estate_factory_threads_cm(monkeypatch):
    from strands.agent.conversation_manager import SummarizingConversationManager

    captured = _capture_agent(monkeypatch)
    # keep hermetic: estate builds its router inline → avoid real Bedrock model resolution
    monkeypatch.setattr(
        "finops_core.models.router.ModelRouter.for_role", lambda self, role: object()
    )
    from devops_core.agents.estate import build_estate_agent

    build_estate_agent(cfg=Config(), tools=[], memory=False)
    assert isinstance(captured["conversation_manager"], SummarizingConversationManager)


# --- CLI --summarize/--no-summarize flag (tri-state: None=config) ----------
def test_finops_ask_summarize_flag():
    from finops_core.cli import _build_parser

    p = _build_parser()
    assert p.parse_args(["ask", "q"]).summarize is None
    assert p.parse_args(["ask", "q", "--summarize"]).summarize is True
    assert p.parse_args(["ask", "q", "--no-summarize"]).summarize is False


def test_devops_ask_summarize_flag():
    from devops_core.cli import _build_parser

    p = _build_parser()
    assert p.parse_args(["ask", "q"]).summarize is None
    assert p.parse_args(["ask", "q", "--summarize"]).summarize is True
    assert p.parse_args(["ask", "q", "--no-summarize"]).summarize is False
