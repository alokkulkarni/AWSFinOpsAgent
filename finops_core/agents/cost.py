"""Cost-Analysis specialist agent (Strands). In the hierarchical design this is wrapped as a
tool of the orchestrator; for Phase 1 it is also usable standalone via `finops ask`."""
from __future__ import annotations

from typing import Optional

from finops_core.config import Config
from finops_core.models.router import ModelRouter
from finops_core.tools.cost import build_cost_tools

_DEFAULT = object()  # sentinel: leave Strands' default (streaming) callback handler in place


def build_cost_agent(
    session=None,
    cfg: Optional[Config] = None,
    router: Optional[ModelRouter] = None,
    callback_handler=_DEFAULT,
    tools=None,
    name: str = "Cost-Analysis Agent",
    description: Optional[str] = None,
):
    """Construct the Cost-Analysis agent bound to the resolved model.

    tools: defaults to in-process Cost Explorer tools; pass a list (e.g. MCP-served tools
           resolved from the cost-tools server) to run distributed.
    callback_handler=None suppresses token streaming (CLI/A2A print the final answer once).
    name/description populate the A2A agent card when served as a sub-agent.
    """
    from strands import Agent  # lazy import: requires the `agent` extra

    from finops_core.agents.prompts import COST_ANALYSIS_PROMPT

    cfg = cfg or Config.load()
    router = router or ModelRouter(cfg, session)
    if tools is None:
        tools = build_cost_tools(session, cfg)
    kwargs = {} if callback_handler is _DEFAULT else {"callback_handler": callback_handler}
    return Agent(
        model=router.for_role("cost"),
        name=name,
        description=description or (
            "Answers AWS cost questions: cost-per-service, drill-down, trends, and forecasts."
        ),
        system_prompt=COST_ANALYSIS_PROMPT,
        tools=tools,
        **kwargs,
    )
