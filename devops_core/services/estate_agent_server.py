"""DevOps/Estate specialist as a distributed A2A server (consumes devops-tools over MCP).

Run: devops serve devops-agent
Env: DEVOPS_TOOLS_URL (http://devops-tools:8085/mcp), FINOPS_A2A_HOST (0.0.0.0),
     FINOPS_A2A_PORT (9005), FINOPS_A2A_PUBLIC_URL (http://devops-agent:9005).
"""
from __future__ import annotations

import os

from finops_core.config import Config
from finops_core.services.mcp_connect import connect_mcp_tools
from devops_core.agents.estate import build_estate_agent


def main() -> None:
    from strands.multiagent.a2a import A2AServer

    cfg = Config.load()
    mcp_url = os.getenv("DEVOPS_TOOLS_URL", "http://127.0.0.1:8085/mcp")
    host = os.getenv("FINOPS_A2A_HOST", "127.0.0.1")
    port = int(os.getenv("FINOPS_A2A_PORT", "9005"))
    public = os.getenv("FINOPS_A2A_PUBLIC_URL")

    tools = connect_mcp_tools(mcp_url)
    agent = build_estate_agent(cfg=cfg, callback_handler=None, tools=tools)

    server = A2AServer(agent=agent, host=host, port=port,
                       http_url=public, serve_at_root=bool(public))
    print(f"[devops-agent] A2A on {host}:{port} (public={public}) tools={len(tools)}")
    server.serve()


if __name__ == "__main__":
    main()
