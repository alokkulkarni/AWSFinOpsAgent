"""DevOps/Estate specialist agent (Strands) — reuses the FinOps ModelRouter + hooks."""
from __future__ import annotations

from typing import Optional

from finops_core.config import Config
from finops_core.models.router import ModelRouter

_DEFAULT = object()


def build_estate_agent(session=None, cfg: Optional[Config] = None, callback_handler=_DEFAULT,
                       tools=None, hooks=None, name: str = "DevOps Estate Agent",
                       description: Optional[str] = None):
    from strands import Agent

    from finops_core.hooks import default_hooks
    from devops_core.steering import load_steering
    from devops_core.tools.estate import build_estate_tools

    cfg = cfg or Config.load()
    if tools is None:
        tools = build_estate_tools(session, cfg)
    if hooks is None:
        hooks = default_hooks(cfg)
    kwargs = {} if callback_handler is _DEFAULT else {"callback_handler": callback_handler}
    return Agent(
        model=ModelRouter(cfg, session).for_role("devops"),
        name=name,
        description=description or (
            "Answers questions about the AWS estate: components, services, resources, topology."
        ),
        system_prompt=load_steering("devops"),
        tools=tools,
        hooks=hooks,
        **kwargs,
    )
