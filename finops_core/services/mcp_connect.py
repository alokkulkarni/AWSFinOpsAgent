"""Helper: connect to a remote MCP tool server and return its tools, with startup retries
(containers may race). Keeps the client referenced for the process lifetime."""
from __future__ import annotations

import time

_clients: list = []  # keep MCP clients alive for the process lifetime


def connect_mcp_tools(url: str, attempts: int = 15, delay: float = 2.0):
    from mcp.client.streamable_http import streamablehttp_client
    from strands.tools.mcp import MCPClient

    last_err = None
    for i in range(1, attempts + 1):
        client = MCPClient(lambda u=url: streamablehttp_client(u))
        try:
            client.start()
            tools = client.list_tools_sync()
            _clients.append(client)  # prevent GC / keep session open
            print(f"[mcp] connected to {url}: {len(tools)} tools")
            return tools
        except Exception as e:  # server not ready yet
            last_err = e
            try:
                client.stop()
            except Exception:
                pass
            print(f"[mcp] {url} not ready (attempt {i}/{attempts}): {type(e).__name__}")
            time.sleep(delay)
    raise RuntimeError(f"could not connect to MCP server {url}: {last_err}")
