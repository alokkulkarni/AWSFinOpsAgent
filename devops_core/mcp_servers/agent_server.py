"""DevSecOps estate agent as an MCP server — the "ask the estate agent" surface for IDEs.

Exposes one tool, ``ask_devops``, that runs the estate agent (inventory + topology + review +
diagnose tools, with its steering, skills, and memory). Inventory figures come from the
deterministic estate tool layer; the agent explains, explores, and draws.

This is the high-level counterpart to the raw `devops-tools` MCP server (individual estate tools
the IDE's own model orchestrates). See ``docs/IDE_INTEGRATION.md``.

Run (stdio, for an IDE):   devops serve ask --stdio
Run (HTTP, for the stack): devops serve ask        # DEVOPS_ASK_MCP_PORT (default 8095)
"""
from __future__ import annotations

import os

from mcp.server import FastMCP

mcp = FastMCP(
    "devops-agent",
    host=os.getenv("FINOPS_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("DEVOPS_ASK_MCP_PORT", "8095")),
)

# Built lazily on first call (the estate scan is expensive), then reused — so within an IDE
# session the agent keeps its conversation + scanned estate across questions.
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        from finops_core.config import Config
        from devops_core.agents.estate import build_estate_agent
        _agent = build_estate_agent(cfg=Config.load(), callback_handler=None)
    return _agent


@mcp.tool(description=(
    "Ask the AWS DevSecOps/estate agent about your AWS estate: what's deployed, resource details, "
    "network topology, security/cost review, or to diagnose an issue (e.g. 'how many EC2 "
    "instances and where?', 'review my RDS setup', 'draw the network in eu-west-2'). Inventory "
    "is exact (tool layer); the agent explains and explores."
))
def ask_devops(question: str) -> str:
    return str(_get_agent()(question)).strip()


def main() -> None:
    from finops_core.mcp_servers._runtime import run_mcp
    run_mcp(mcp, "devops-agent")


if __name__ == "__main__":
    main()
