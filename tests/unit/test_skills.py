"""Agent Skills: discovery, the directory-scoped reader's path guard, config gating, and the
guarantee that the agent factories thread the AgentSkills plugin ONLY when enabled (default-off
→ existing agent behavior is byte-for-byte unchanged)."""
from pathlib import Path

import pytest

from finops_core.config import Config
from finops_core.skills import (
    ANOMALY_SKILLS_DIR,
    COST_SKILLS_DIR,
    OPTIMIZE_SKILLS_DIR,
    attach_skills,
    has_skills,
    list_skills,
    read_under_root,
    skill_metadata,
    skills_active,
)
from devops_core.skills import ESTATE_SKILLS_DIR

# Each agent's seed skill folder → the skill it must contain.
SEED = {
    COST_SKILLS_DIR: "cost-drilldown-playbook",
    OPTIMIZE_SKILLS_DIR: "savings-plan-vs-ri",
    ANOMALY_SKILLS_DIR: "anomaly-triage",
    ESTATE_SKILLS_DIR: "incident-triage-runbook",
}


# --- discovery -------------------------------------------------------------
@pytest.mark.parametrize("root,expected", SEED.items())
def test_seed_skill_discovered(root, expected):
    assert has_skills(root)
    assert expected in {s["name"] for s in list_skills(root)}


@pytest.mark.parametrize("root,expected", SEED.items())
def test_skill_name_matches_directory(root, expected):
    """The Agent Skills spec requires a skill's name == its directory name; description required."""
    skill_dir = Path(root) / expected
    meta = skill_metadata(skill_dir)
    assert meta["name"] == skill_dir.name
    assert meta["description"].strip()


def test_strands_loader_agrees_with_ours():
    """Cross-check the pure-python parser against the SDK's own directory loader."""
    from strands import Skill

    ours = {s["name"] for s in list_skills(OPTIMIZE_SKILLS_DIR)}
    theirs = {s.name for s in Skill.from_directory(str(OPTIMIZE_SKILLS_DIR))}
    assert "savings-plan-vs-ri" in (ours & theirs)


def test_empty_dir_has_no_skills(tmp_path):
    assert not has_skills(tmp_path)
    assert list_skills(tmp_path) == []


# --- scoped reader path guard (least privilege) ----------------------------
def test_reader_reads_reference_inside_root():
    out = read_under_root(OPTIMIZE_SKILLS_DIR, "savings-plan-vs-ri/references/breakeven.md")
    assert "break-even" in out.lower()


def test_reader_accepts_absolute_path_inside_root():
    abs_path = Path(OPTIMIZE_SKILLS_DIR) / "savings-plan-vs-ri" / "SKILL.md"
    assert "Savings Plans" in read_under_root(OPTIMIZE_SKILLS_DIR, str(abs_path))


@pytest.mark.parametrize(
    "bad",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "../cost/cost-drilldown-playbook/SKILL.md",  # another agent's skills are out of reach
    ],
)
def test_reader_rejects_path_escape(bad):
    with pytest.raises(ValueError):
        read_under_root(OPTIMIZE_SKILLS_DIR, bad)


def test_reader_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        read_under_root(OPTIMIZE_SKILLS_DIR, "savings-plan-vs-ri/references/nope.md")


# --- config gating (default OFF) ------------------------------------------
def test_skills_disabled_by_default():
    assert Config().skills_enabled is False
    assert skills_active(Config()) is False


def test_env_enables_skills(monkeypatch):
    monkeypatch.setenv("FINOPS_SKILLS", "true")
    assert Config.load().skills_enabled is True


def test_skills_active_override_wins():
    cfg = Config()  # disabled
    assert skills_active(cfg, override=True) is True
    assert skills_active(cfg, override=False) is False


# --- attach_skills helper --------------------------------------------------
def test_attach_skills_noop_when_disabled():
    tools = [object()]
    out_tools, kwargs = attach_skills(tools, COST_SKILLS_DIR, enabled=False)
    assert out_tools is tools and kwargs == {}


def test_attach_skills_adds_plugin_and_reader_when_enabled():
    tools = [object()]
    out_tools, kwargs = attach_skills(tools, COST_SKILLS_DIR, enabled=True)
    assert len(kwargs["plugins"]) == 1
    assert len(out_tools) == len(tools) + 1  # scoped reader appended


def test_attach_skills_noop_when_no_skills(tmp_path):
    tools = [object()]
    out_tools, kwargs = attach_skills(tools, tmp_path, enabled=True)
    assert out_tools is tools and kwargs == {}


# --- factory threading (monkeypatched Agent → no Bedrock) ------------------
class _FakeRouter:
    def for_role(self, role):  # ModelRouter normally returns a (lazy) BedrockModel
        return object()


def _capture_agent(monkeypatch):
    captured = {}

    class FakeAgent:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr("strands.Agent", FakeAgent)
    return captured


def test_cost_factory_default_off_changes_nothing(monkeypatch):
    captured = _capture_agent(monkeypatch)
    from finops_core.agents.cost import build_cost_agent

    build_cost_agent(router=_FakeRouter(), tools=[], cfg=Config())
    assert "plugins" not in captured
    assert captured["tools"] == []  # no scoped reader appended


def test_cost_factory_skills_on_adds_plugin_and_reader(monkeypatch):
    captured = _capture_agent(monkeypatch)
    from finops_core.agents.cost import build_cost_agent

    build_cost_agent(router=_FakeRouter(), tools=[], cfg=Config(), skills=True)
    assert len(captured["plugins"]) == 1
    assert len(captured["tools"]) == 1


@pytest.mark.parametrize(
    "factory_path,builder",
    [
        ("finops_core.agents.optimize", "build_optimize_agent"),
        ("finops_core.agents.anomaly", "build_anomaly_agent"),
    ],
)
def test_other_finops_factories_thread_skills(monkeypatch, factory_path, builder):
    captured = _capture_agent(monkeypatch)
    import importlib

    build = getattr(importlib.import_module(factory_path), builder)
    build(router=_FakeRouter(), tools=[], cfg=Config(), skills=True)
    assert len(captured["plugins"]) == 1
    assert len(captured["tools"]) == 1


# --- CLI --skills/--no-skills flag (tri-state: None=config) ----------------
def test_finops_ask_skills_flag():
    from finops_core.cli import _build_parser

    p = _build_parser()
    assert p.parse_args(["ask", "q"]).skills is None
    assert p.parse_args(["ask", "q", "--skills"]).skills is True
    assert p.parse_args(["ask", "q", "--no-skills"]).skills is False


def test_devops_ask_skills_flag():
    from devops_core.cli import _build_parser

    p = _build_parser()
    assert p.parse_args(["ask", "q"]).skills is None
    assert p.parse_args(["ask", "q", "--skills"]).skills is True
    assert p.parse_args(["ask", "q", "--no-skills"]).skills is False


def test_estate_factory_threads_skills(monkeypatch):
    captured = _capture_agent(monkeypatch)
    # estate builds its router inline; keep the test hermetic (no Bedrock model resolution).
    monkeypatch.setattr(
        "finops_core.models.router.ModelRouter.for_role", lambda self, role: object()
    )
    from devops_core.agents.estate import build_estate_agent

    build_estate_agent(tools=[], cfg=Config(), skills=True)
    assert len(captured["plugins"]) == 1
    assert len(captured["tools"]) == 1
    # and default-off stays a no-op
    captured.clear()
    build_estate_agent(tools=[], cfg=Config())
    assert "plugins" not in captured and captured["tools"] == []
