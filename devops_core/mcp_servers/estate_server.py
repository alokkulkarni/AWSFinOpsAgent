"""devops-estate-tools MCP server (distributed tool tier).

Builds an EstateIndex at startup (scans the estate once) and serves the query tools over MCP.
Run: devops serve devops-tools
Env: FINOPS_MCP_HOST (0.0.0.0), DEVOPS_MCP_PORT (8085), DEVOPS_SCAN_REGIONS (comma list; default all).
"""
from __future__ import annotations

import os

from mcp.server import FastMCP

from finops_core.aws.session import build_session
from finops_core.config import Config
from devops_core.discovery.index import EstateIndex

_cfg = Config.load()
_regions = os.getenv("DEVOPS_SCAN_REGIONS")
_index = EstateIndex(
    build_session(_cfg), _cfg,
    regions=[r.strip() for r in _regions.split(",")] if _regions else None,
    fan_out=os.getenv("DEVOPS_FAN_OUT", "").lower() in ("1", "true", "yes"),
    role_name=os.getenv("DEVOPS_MEMBER_ROLE", "OrganizationAccountAccessRole"),
)

mcp = FastMCP(
    "devops-estate-tools",
    host=os.getenv("FINOPS_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("DEVOPS_MCP_PORT", "8085")),
)


@mcp.tool(description="AWS estate summary: total resources + counts by service / region / account.")
def get_estate_summary() -> dict:
    return _index.summary()


@mcp.tool(description="List estate resources filtered by service / resource_type / region / account.")
def list_resources(service: str = "", resource_type: str = "", region: str = "",
                   account: str = "", limit: int = 50) -> dict:
    return _index.list(service=service or None, resource_type=resource_type or None,
                       region=region or None, account=account or None, limit=limit)


@mcp.tool(description="Look up one resource by id or ARN.")
def describe_resource(id_or_arn: str) -> dict:
    return _index.describe(id_or_arn)


@mcp.tool(description="Search the estate by id, name, ARN, service, type, or tag value.")
def find_resource(query: str, limit: int = 20) -> dict:
    return _index.find(query, limit=limit)


@mcp.tool(description="Network topology of a region: VPCs -> subnets -> instances, IGW/NAT/peering.")
def get_topology(region: str) -> dict:
    from devops_core.discovery.topology import TopologyScanner
    return TopologyScanner(build_session(_cfg), _cfg).scan(region).to_dict()


def main() -> None:
    from finops_core.mcp_servers._runtime import run_mcp
    run_mcp(mcp, "devops-tools")


if __name__ == "__main__":
    main()
