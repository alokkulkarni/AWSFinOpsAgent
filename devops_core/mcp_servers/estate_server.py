"""devops-estate-tools MCP server (distributed tool tier).

Builds an EstateIndex per credential set (scanned once per user, then cached) and
serves the query tools over MCP.

Run: devops serve devops-tools
Env: FINOPS_MCP_HOST (0.0.0.0), DEVOPS_MCP_PORT (8085), DEVOPS_SCAN_REGIONS (comma list; default all).

Connector mode: users pass their own AWS credentials via X-Aws-* request headers.
  The EstateIndex is built lazily on the first tool call per credential set and cached
  for the lifetime of the process (maxsize=20 distinct credential sets).
Server-side mode (local dev / Docker stack): single shared index, scanned once at first use.
"""
from __future__ import annotations

import os

from mcp.server import FastMCP
from mcp.server.fastmcp import Context

from finops_core.config import Config
from finops_core.mcp_servers.connector_auth import cred_key_from_context, session_from_context
from devops_core.discovery.index import EstateIndex

_cfg = Config.load()

# Credential-keyed index cache: one EstateIndex per unique credential set.
# EstateIndex is lazy — the actual AWS scan happens on first estate() call, not here.
_index_cache: dict[str, EstateIndex] = {}
_MAX_CACHED_SESSIONS = 20

mcp = FastMCP(
    "devops-estate-tools",
    host=os.getenv("FINOPS_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("DEVOPS_MCP_PORT", "8085")),
)


def _get_index(ctx) -> EstateIndex:
    """Return (or lazily create) the EstateIndex for this request's credential set."""
    key = cred_key_from_context(ctx, _cfg)
    if key not in _index_cache:
        if len(_index_cache) >= _MAX_CACHED_SESSIONS:
            # Evict oldest entry (simple FIFO) to bound memory usage.
            _index_cache.pop(next(iter(_index_cache)))
        scan_regions = os.getenv("DEVOPS_SCAN_REGIONS")
        _index_cache[key] = EstateIndex(
            session=session_from_context(ctx, _cfg),
            cfg=_cfg,
            regions=[r.strip() for r in scan_regions.split(",")] if scan_regions else None,
            fan_out=os.getenv("DEVOPS_FAN_OUT", "").lower() in ("1", "true", "yes"),
            role_name=os.getenv("DEVOPS_MEMBER_ROLE", "OrganizationAccountAccessRole"),
        )
    return _index_cache[key]


@mcp.tool(description="AWS estate summary: total resources + counts by service / region / account.")
def get_estate_summary(ctx: Context = None) -> dict:
    return _get_index(ctx).summary()


@mcp.tool(description="List estate resources filtered by service / resource_type / region / account.")
def list_resources(service: str = "", resource_type: str = "", region: str = "",
                   account: str = "", limit: int = 50, ctx: Context = None) -> dict:
    return _get_index(ctx).list(service=service or None, resource_type=resource_type or None,
                                region=region or None, account=account or None, limit=limit)


@mcp.tool(description="Look up one resource by id or ARN.")
def describe_resource(id_or_arn: str, ctx: Context = None) -> dict:
    return _get_index(ctx).describe(id_or_arn)


@mcp.tool(description="Search the estate by id, name, ARN, service, type, or tag value.")
def find_resource(query: str, limit: int = 20, ctx: Context = None) -> dict:
    return _get_index(ctx).find(query, limit=limit)


@mcp.tool(description="Network topology of a region: VPCs -> subnets -> instances, IGW/NAT/peering.")
def get_topology(region: str, ctx: Context = None) -> dict:
    from devops_core.discovery.topology import TopologyScanner
    return TopologyScanner(session_from_context(ctx, _cfg), _cfg).scan(region).to_dict()


def main() -> None:
    from finops_core.mcp_servers._runtime import run_mcp
    run_mcp(mcp, "devops-tools")


if __name__ == "__main__":
    main()
