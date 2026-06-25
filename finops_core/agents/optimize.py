"""Optimization specialist agent (Strands)."""
from __future__ import annotations

from typing import Optional

from finops_core.config import Config
from finops_core.models.router import ModelRouter
from finops_core.skills import OPTIMIZE_SKILLS_DIR, attach_skills, skills_active
from finops_core.tools.optimize import build_optimize_tools

_DEFAULT = object()


def build_optimize_agent(
    session=None,
    cfg: Optional[Config] = None,
    router: Optional[ModelRouter] = None,
    callback_handler=_DEFAULT,
    tools=None,
    name: str = "Optimization Agent",
    description: Optional[str] = None,
    hooks=None,
    skills: Optional[bool] = None,
    conversation: Optional[bool] = None,
    memory: Optional[bool] = None,
):
    """Cost-savings specialist. tools defaults to in-process Optimizer tools; pass MCP-served
    tools to run distributed. skills: None → cfg.skills_enabled (default off); True/False forces.
    conversation/memory: None → config default (both ON); True/False force."""
    from strands import Agent

    from finops_core.agent_context import agent_context_kwargs
    from finops_core.agents.prompts import OPTIMIZATION_PROMPT
    from finops_core.hooks import default_hooks

    cfg = cfg or Config.load()
    router = router or ModelRouter(cfg, session)
    if tools is None:
        tools = build_optimize_tools(session, cfg)
    if hooks is None:
        hooks = default_hooks(cfg)
    tools, skill_kwargs = attach_skills(
        tools, OPTIMIZE_SKILLS_DIR, enabled=skills_active(cfg, skills)
    )
    ctx_kwargs = agent_context_kwargs(
        cfg, "finops", router=router, conversation=conversation, memory=memory
    )
    kwargs = {} if callback_handler is _DEFAULT else {"callback_handler": callback_handler}
    return Agent(
        model=router.for_role("optimization"),
        name=name,
        description=description or (
            "Finds and ranks AWS cost-savings: rightsizing, idle cleanup, Savings Plans/RI, "
            "Compute Optimizer, Trusted Advisor."
        ),
        system_prompt=OPTIMIZATION_PROMPT,
        tools=tools,
        hooks=hooks,
        **skill_kwargs,
        **ctx_kwargs,
        **kwargs,
    )
