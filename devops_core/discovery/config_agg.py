"""AWS Config aggregator source — richest inventory + relationships when recording is enabled."""
from __future__ import annotations

from finops_core.aws.session import client
from devops_core.schemas.estate import Resource


def first_aggregator(session, region: str = "us-east-1"):
    cs = client(session, "config", region=region)
    aggs = cs.describe_configuration_aggregators().get("ConfigurationAggregators", [])
    return aggs[0]["ConfigurationAggregatorName"] if aggs else None


def discovered_count(session, aggregator: str, region: str = "us-east-1") -> int:
    cs = client(session, "config", region=region)
    return cs.get_aggregate_discovered_resource_counts(
        ConfigurationAggregatorName=aggregator).get("TotalDiscoveredResources", 0)


def list_resources(session, aggregator: str, region: str = "us-east-1", max_pages: int = 50) -> list:
    """Use the SQL SelectAggregate API to pull resources (only worthwhile if count > 0)."""
    cs = client(session, "config", region=region)
    sql = ("SELECT resourceId, resourceType, resourceName, awsRegion, accountId, arn "
           "WHERE resourceType > ''")
    out: list = []
    token, pages = None, 0
    while pages < max_pages:
        kwargs = {"Expression": sql, "ConfigurationAggregatorName": aggregator, "Limit": 100}
        if token:
            kwargs["NextToken"] = token
        resp = cs.select_aggregate_resource_config(**kwargs)
        import json
        for row in resp.get("Results", []):
            d = json.loads(row)
            out.append(Resource(
                service=(d.get("resourceType", "AWS::?::?").split("::")[1] or "?").lower(),
                resource_type=d.get("resourceType", "?"),
                id=d.get("resourceId", "?"),
                arn=d.get("arn"),
                region=d.get("awsRegion"),
                account=d.get("accountId"),
                name=d.get("resourceName"),
            ))
        token = resp.get("NextToken")
        pages += 1
        if not token:
            break
    return out
