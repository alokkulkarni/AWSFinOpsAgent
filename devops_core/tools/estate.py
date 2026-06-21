"""Estate Q&A tools — thin wrappers over EstateIndex, returning JSON-serializable dicts."""
from __future__ import annotations

from typing import Optional

from devops_core.discovery.index import EstateIndex


def build_estate_tools(session=None, cfg=None, index: Optional[EstateIndex] = None):
    from strands import tool

    index = index or EstateIndex(session, cfg)

    @tool
    def get_estate_summary() -> dict:
        """High-level AWS estate summary: total resource count, counts by service / region /
        account, and the discovery sources used. Call this first for "what's in my estate"."""
        return index.summary()

    @tool
    def list_resources(service: str = "", resource_type: str = "", region: str = "",
                       account: str = "", limit: int = 50) -> dict:
        """List estate resources, optionally filtered by service (ec2, lambda, s3, ecs, rds, ...),
        resource_type (e.g. ec2:subnet), region, or account. Returns count + the resources."""
        return index.list(service=service or None, resource_type=resource_type or None,
                          region=region or None, account=account or None, limit=limit)

    @tool
    def describe_resource(id_or_arn: str) -> dict:
        """Look up a single resource by its id or ARN (returns type, region, account, tags, ...)."""
        return index.describe(id_or_arn)

    @tool
    def find_resource(query: str, limit: int = 20) -> dict:
        """Search the estate by id, name, ARN, service, resource type, or tag value."""
        return index.find(query, limit=limit)

    @tool
    def get_topology(region: str) -> dict:
        """Network topology of a region: VPCs -> subnets -> instances, with IGW/NAT/endpoints
        and VPC peering. Use for "show my network/VPC layout in <region>"."""
        from finops_core.config import Config
        from devops_core.discovery.topology import TopologyScanner
        return TopologyScanner(session, cfg or Config()).scan(region).to_dict()

    return [get_estate_summary, list_resources, describe_resource, find_resource, get_topology]
