"""FinOps Orchestrator as a distributed A2A server.

Discovers specialist sub-agents over A2A (Cost-Analysis today) and routes questions to them.
Exposed itself over A2A so the API gateway / UI / CLI can call it as the single entrypoint.

Run: python -m finops_core.services.orchestrator_server
Env: FINOPS_COST_AGENT_URL (http://cost-agent:9001), FINOPS_A2A_HOST (0.0.0.0),
     FINOPS_A2A_PORT (9000), FINOPS_A2A_PUBLIC_URL (http://orchestrator:9000).
"""
from __future__ import annotations

import os

from finops_core.config import Config
from finops_core.models.router import ModelRouter


def main() -> None:
    from strands import Agent
    from strands.multiagent.a2a import A2AServer
    from strands_tools.a2a_client import A2AClientToolProvider

    from finops_core.agents.prompts import ORCHESTRATOR_PROMPT

    cfg = Config.load()
    host = os.getenv("FINOPS_A2A_HOST", "127.0.0.1")
    port = int(os.getenv("FINOPS_A2A_PORT", "9000"))
    public = os.getenv("FINOPS_A2A_PUBLIC_URL")

    # Known specialist sub-agents (A2A). Add more as later phases land.
    known = [os.getenv("FINOPS_COST_AGENT_URL", "http://127.0.0.1:9001")]
    for env in ("FINOPS_OPTIMIZE_AGENT_URL", "FINOPS_ANOMALY_AGENT_URL"):
        if os.getenv(env):
            known.append(os.environ[env])

    # A2A client tools: discovery + delegation to known specialist agents.
    provider = A2AClientToolProvider(known_agent_urls=known)
    agent = Agent(
        model=ModelRouter(cfg).for_role("orchestrator"),
        name="FinOps Orchestrator",
        description="Routes AWS FinOps questions to specialist agents (cost, optimization, ...).",
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=provider.tools,
        callback_handler=None,
    )

    server = A2AServer(
        agent=agent, host=host, port=port,
        http_url=public, serve_at_root=bool(public),
    )
    print(f"[orchestrator] A2A on {host}:{port} (public={public}) -> sub-agents {known}")
    server.serve()


if __name__ == "__main__":
    main()
