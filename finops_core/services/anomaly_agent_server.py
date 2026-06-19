"""Anomaly & Budget specialist as a distributed A2A server (consumes anomaly-tools over MCP).

Run: finops serve anomaly-agent
Env: FINOPS_ANOMALY_TOOLS_URL (http://anomaly-tools:8083/mcp), FINOPS_A2A_HOST (0.0.0.0),
     FINOPS_A2A_PORT (9003), FINOPS_A2A_PUBLIC_URL (http://anomaly-agent:9003).
"""
from __future__ import annotations

import os

from finops_core.agents.anomaly import build_anomaly_agent
from finops_core.config import Config
from finops_core.services.mcp_connect import connect_mcp_tools


def main() -> None:
    from strands.multiagent.a2a import A2AServer

    cfg = Config.load()
    mcp_url = os.getenv("FINOPS_ANOMALY_TOOLS_URL", "http://127.0.0.1:8083/mcp")
    host = os.getenv("FINOPS_A2A_HOST", "127.0.0.1")
    port = int(os.getenv("FINOPS_A2A_PORT", "9003"))
    public = os.getenv("FINOPS_A2A_PUBLIC_URL")

    tools = connect_mcp_tools(mcp_url)
    agent = build_anomaly_agent(cfg=cfg, callback_handler=None, tools=tools)

    server = A2AServer(agent=agent, host=host, port=port,
                       http_url=public, serve_at_root=bool(public))
    print(f"[anomaly-agent] A2A on {host}:{port} (public={public}) tools={len(tools)}")
    server.serve()


if __name__ == "__main__":
    main()
