"""FinOps agent as an MCP server — the high-level "ask the agent" surface for IDEs.

Exposes one tool, ``ask_finops``, that runs the deterministic ``IntentRouter`` (which classifies
the question and forwards it to the right specialist — cost / optimization / anomaly-budget — with
that specialist's steering, skills, and memory). Returns the specialist's answer; all figures
inside come from the deterministic tool layer (numbers-must-be-exact).

This is what Claude Code / Cursor / VS Code call when you want *the FinOps agent*, as opposed to
the raw `cost-tools` MCP server (individual tools the IDE's own model orchestrates). See
``docs/IDE_INTEGRATION.md``.

Run (stdio, for an IDE):   finops serve ask --stdio
Run (HTTP, for the stack): finops serve ask        # FINOPS_ASK_MCP_PORT (default 8090)
"""
from __future__ import annotations

import os

from mcp.server import FastMCP

mcp = FastMCP(
    "finops-agent",
    host=os.getenv("FINOPS_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("FINOPS_ASK_MCP_PORT", "8090")),
)

# Built lazily on first call (keeps import + IDE startup cheap and AWS-free until a question
# actually arrives), then reused so cross-call cost is just the agent run.
_router = None


def _get_router():
    global _router
    if _router is None:
        from finops_core.config import Config
        from finops_core.router import IntentRouter
        _router = IntentRouter(Config.load())
    return _router


@mcp.tool(description=(
    "Ask the AWS FinOps agent a natural-language question about spend, cost drivers, savings, "
    "anomalies, or budgets (e.g. 'where is my money going this month?', 'how do I cut my bill?', "
    "'am I over budget?'). Routes to the right specialist and returns an analysis whose figures "
    "come straight from Cost Explorer (exact, not estimated)."
))
def ask_finops(question: str) -> str:
    intent, answer = _get_router().answer(question)
    return f"[{intent} specialist]\n{answer}"


def main() -> None:
    from finops_core.mcp_servers._runtime import run_mcp
    run_mcp(mcp, "finops-agent")


if __name__ == "__main__":
    main()
