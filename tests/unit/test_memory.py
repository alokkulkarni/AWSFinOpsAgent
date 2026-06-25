"""Persistent agent memory: the local JSON store (add/search/redaction/dedupe/persistence),
config gating (ON by default), the ``attach_memory`` helper, and the guarantee that the agent
factories thread a MemoryManager ON by default and omit it when turned off."""
import asyncio
import importlib
import json

import pytest

from finops_core.config import Config
from finops_core.memory import attach_memory, memory_active, memory_path, redact_account_ids
from finops_core.memory.store import LocalJSONMemoryStore


def _run(coro):
    return asyncio.run(coro)


def _store(tmp_path, **kw):
    kw.setdefault("name", "finops")
    kw.setdefault("description", "test store")
    return LocalJSONMemoryStore(path=tmp_path / "finops.json", **kw)


# --- store: add → search ---------------------------------------------------
def test_add_then_search_orders_by_relevance(tmp_path):
    s = _store(tmp_path)
    _run(s.add("our prod account is the invincible payer"))
    _run(s.add("athena scan cap is 10 GB per query"))
    _run(s.add("EC2 is the top spending service this month"))
    hits = _run(s.search("which account is prod"))
    assert hits, "expected at least one match"
    assert "invincible" in hits[0].content  # best token overlap ranks first


def test_search_respects_max_results(tmp_path):
    s = _store(tmp_path, max_search_results=2)
    for i in range(5):
        _run(s.add(f"fact number {i} about cost"))
    assert len(_run(s.search("cost fact"))) <= 2


def test_search_missing_file_returns_empty(tmp_path):
    assert _run(_store(tmp_path).search("anything")) == []


# --- store: secrets hygiene (account-id redaction on write) ----------------
def test_account_id_redacted_on_write(tmp_path):
    s = _store(tmp_path, redact=True)
    _run(s.add("account 123456789012 is production"))
    raw = (tmp_path / "finops.json").read_text()
    assert "123456789012" not in raw
    assert "************" in raw


def test_redaction_can_be_disabled(tmp_path):
    s = _store(tmp_path, redact=False)
    _run(s.add("account 123456789012 is production"))
    assert "123456789012" in (tmp_path / "finops.json").read_text()


def test_redact_helper_is_pure():
    assert redact_account_ids("id 123456789012 here") == "id ************ here"
    assert redact_account_ids("no ids here") == "no ids here"


# --- store: persistence + dedupe ------------------------------------------
def test_persistence_round_trip(tmp_path):
    _run(_store(tmp_path).add("remember the digest goes to slack"))
    reloaded = _store(tmp_path)  # fresh instance, same path
    hits = _run(reloaded.search("where does the digest go"))
    assert any("slack" in h.content for h in hits)


def test_identical_content_deduped(tmp_path):
    s = _store(tmp_path)
    _run(s.add("EC2 is the top spender"))
    _run(s.add("EC2 is the top spender"))
    entries = json.loads((tmp_path / "finops.json").read_text())
    assert len(entries) == 1


# --- config gating (ON by default) ----------------------------------------
def test_memory_on_by_default():
    cfg = Config()
    assert cfg.memory.enabled is True
    assert memory_active(cfg) is True


def test_env_disables_memory(monkeypatch):
    monkeypatch.setenv("FINOPS_MEMORY", "false")
    assert Config.load().memory.enabled is False


def test_memory_active_override_wins():
    cfg = Config()
    assert memory_active(cfg, override=False) is False
    cfg.memory.enabled = False
    assert memory_active(cfg, override=True) is True


def test_memory_path_expands_and_namespaces(tmp_path):
    cfg = Config()
    cfg.memory.dir = str(tmp_path)
    assert memory_path(cfg, "finops") == tmp_path / "finops.json"
    assert memory_path(cfg, "devops") == tmp_path / "devops.json"


# --- attach_memory helper --------------------------------------------------
def test_attach_memory_noop_when_disabled(tmp_path):
    cfg = Config()
    cfg.memory.dir = str(tmp_path)
    assert attach_memory(cfg, "finops", enabled=False) == {}


def test_attach_memory_wires_manager_when_enabled(tmp_path):
    from strands.memory import MemoryManager

    cfg = Config()
    cfg.memory.dir = str(tmp_path)
    kwargs = attach_memory(cfg, "finops", enabled=True)
    assert isinstance(kwargs["memory_manager"], MemoryManager)


# --- factory threading (monkeypatched Agent → no Bedrock) ------------------
class _FakeRouter:
    def for_role(self, role):
        return object()


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
def test_finops_factories_thread_memory_by_default(monkeypatch, tmp_path, factory_path, builder):
    from strands.memory import MemoryManager

    captured = _capture_agent(monkeypatch)
    cfg = Config()
    cfg.memory.dir = str(tmp_path)
    build = getattr(importlib.import_module(factory_path), builder)
    build(router=_FakeRouter(), tools=[], cfg=cfg)
    assert isinstance(captured["memory_manager"], MemoryManager)


def test_finops_factory_no_memory_when_off(monkeypatch, tmp_path):
    captured = _capture_agent(monkeypatch)
    cfg = Config()
    cfg.memory.dir = str(tmp_path)
    from finops_core.agents.cost import build_cost_agent

    build_cost_agent(router=_FakeRouter(), tools=[], cfg=cfg, memory=False)
    assert "memory_manager" not in captured


def test_estate_factory_threads_memory(monkeypatch, tmp_path):
    from strands.memory import MemoryManager

    captured = _capture_agent(monkeypatch)
    monkeypatch.setattr(
        "finops_core.models.router.ModelRouter.for_role", lambda self, role: object()
    )
    cfg = Config()
    cfg.memory.dir = str(tmp_path)
    from devops_core.agents.estate import build_estate_agent

    build_estate_agent(cfg=cfg, tools=[], conversation=False)
    assert isinstance(captured["memory_manager"], MemoryManager)


# --- CLI --memory/--no-memory flag (tri-state: None=config) ----------------
def test_finops_ask_memory_flag():
    from finops_core.cli import _build_parser

    p = _build_parser()
    assert p.parse_args(["ask", "q"]).memory is None
    assert p.parse_args(["ask", "q", "--memory"]).memory is True
    assert p.parse_args(["ask", "q", "--no-memory"]).memory is False


def test_devops_ask_memory_flag():
    from devops_core.cli import _build_parser

    p = _build_parser()
    assert p.parse_args(["ask", "q"]).memory is None
    assert p.parse_args(["ask", "q", "--memory"]).memory is True
    assert p.parse_args(["ask", "q", "--no-memory"]).memory is False
