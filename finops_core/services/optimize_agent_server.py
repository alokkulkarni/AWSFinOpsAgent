"""Optimization specialist as a distributed A2A server (consumes optimize-tools over MCP).

Run: python -m finops_core.services.optimize_agent_server  (or: finops serve optimize-agent)
Env: FINOPS_OPTIMIZE_TOOLS_URL (http://optimize-tools:8082/mcp), FINOPS_A2A_HOST (0.0.0.0),
     FINOPS_A2A_PORT (9002), FINOPS_A2A_PUBLIC_URL (http://optimize-agent:9002).
"""
from __future__ import annotations

import os

from finops_core.agents.optimize import build_optimize_agent
from finops_core.config import Config
from finops_core.services.mcp_connect import connect_mcp_tools


def main() -> None:
    from strands.multiagent.a2a import A2AServer

    cfg = Config.load()
    mcp_url = os.getenv("FINOPS_OPTIMIZE_TOOLS_URL", "http://127.0.0.1:8082/mcp")
    host = os.getenv("FINOPS_A2A_HOST", "127.0.0.1")
    port = int(os.getenv("FINOPS_A2A_PORT", "9002"))
    public = os.getenv("FINOPS_A2A_PUBLIC_URL")

    tools = connect_mcp_tools(mcp_url)
    agent = build_optimize_agent(cfg=cfg, callback_handler=None, tools=tools)

    server = A2AServer(agent=agent, host=host, port=port,
                       http_url=public, serve_at_root=bool(public))
    print(f"[optimize-agent] A2A on {host}:{port} (public={public}) tools={len(tools)}")
    server.serve()


if __name__ == "__main__":
    main()
