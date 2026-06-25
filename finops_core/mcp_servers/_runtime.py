"""Shared MCP server runtime helper.

One place to pick the MCP transport so the same servers serve both:
  * the distributed Docker stack  -> ``streamable-http`` (the default; host:port/mcp), and
  * a local IDE (Claude Code / Cursor / VS Code) -> ``stdio`` (the IDE spawns the process).

Critical for stdio: the MCP protocol uses **stdout**, so the startup banner must go to **stderr**
(any stray stdout write corrupts the stream). Selected via ``FINOPS_MCP_TRANSPORT`` (which the
``serve --stdio`` flag sets), defaulting to ``streamable-http`` so existing behavior is unchanged.
"""
from __future__ import annotations

import os
import sys


def run_mcp(mcp, label: str) -> None:
    """Run a FastMCP server with the transport selected by ``FINOPS_MCP_TRANSPORT``."""
    transport = os.getenv("FINOPS_MCP_TRANSPORT", "streamable-http")
    if transport == "stdio":
        print(f"[{label}] MCP stdio (IDE)", file=sys.stderr, flush=True)
        mcp.run(transport="stdio")
        return
    s = mcp.settings
    print(f"[{label}] MCP streamable-http on {s.host}:{s.port}{s.streamable_http_path}",
          file=sys.stderr, flush=True)
    mcp.run(transport="streamable-http")
