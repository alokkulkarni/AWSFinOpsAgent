"""Cost-Analysis specialist as a distributed A2A server.

Connects to the cost-tools MCP server for its tools, then exposes the agent over A2A so the
orchestrator can call it. The agent itself calls Bedrock, so this container needs AWS creds.

Run: python -m finops_core.services.cost_agent_server
Env: FINOPS_COST_TOOLS_URL (http://cost-tools:8081/mcp), FINOPS_A2A_HOST (0.0.0.0),
     FINOPS_A2A_PORT (9001), FINOPS_A2A_PUBLIC_URL (http://cost-agent:9001).
"""
from __future__ import annotations

import os

from finops_core.agents.cost import build_cost_agent
from finops_core.config import Config
from finops_core.services.mcp_connect import connect_mcp_tools


def main() -> None:
    from strands.multiagent.a2a import A2AServer

    cfg = Config.load()
    mcp_url = os.getenv("FINOPS_COST_TOOLS_URL", "http://127.0.0.1:8081/mcp")
    host = os.getenv("FINOPS_A2A_HOST", "127.0.0.1")
    port = int(os.getenv("FINOPS_A2A_PORT", "9001"))
    public = os.getenv("FINOPS_A2A_PUBLIC_URL")

    tools = connect_mcp_tools(mcp_url)
    agent = build_cost_agent(cfg=cfg, callback_handler=None, tools=tools)

    server = A2AServer(
        agent=agent, host=host, port=port,
        http_url=public, serve_at_root=bool(public),
    )
    print(f"[cost-agent] A2A on {host}:{port} (public={public}) tools={len(tools)}")
    server.serve()


if __name__ == "__main__":
    main()
