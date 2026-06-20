"""Anomaly & Budget specialist agent (Strands)."""
from __future__ import annotations

from typing import Optional

from finops_core.config import Config
from finops_core.models.router import ModelRouter
from finops_core.tools.anomaly import build_anomaly_tools

_DEFAULT = object()


def build_anomaly_agent(
    session=None,
    cfg: Optional[Config] = None,
    router: Optional[ModelRouter] = None,
    callback_handler=_DEFAULT,
    tools=None,
    name: str = "Anomaly & Budget Agent",
    description: Optional[str] = None,
    hooks=None,
):
    from strands import Agent

    from finops_core.agents.prompts import ANOMALY_PROMPT
    from finops_core.hooks import default_hooks

    cfg = cfg or Config.load()
    router = router or ModelRouter(cfg, session)
    if tools is None:
        tools = build_anomaly_tools(session, cfg)
    if hooks is None:
        hooks = default_hooks(cfg)
    kwargs = {} if callback_handler is _DEFAULT else {"callback_handler": callback_handler}
    return Agent(
        model=router.for_role("cost"),
        name=name,
        description=description or "Reports AWS cost anomalies and budget status (actual + forecast vs limit).",
        system_prompt=ANOMALY_PROMPT,
        tools=tools,
        hooks=hooks,
        **kwargs,
    )
