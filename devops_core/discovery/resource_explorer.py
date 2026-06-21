"""AWS Resource Explorer source — broad cross-service discovery per region."""
from __future__ import annotations

from finops_core.aws.session import client
from devops_core.schemas.estate import Resource


def search(session, region: str, query: str = "*", max_pages: int = 20) -> list:
    rex = client(session, "resource-explorer-2", region=region)
    resources: list = []
    token, pages = None, 0
    while pages < max_pages:
        kwargs = {"QueryString": query, "MaxResults": 100}
        if token:
            kwargs["NextToken"] = token
        resp = rex.search(**kwargs)
        for r in resp.get("Resources", []):
            tags = {}
            for prop in r.get("Properties", []):
                if prop.get("Name") == "tags":
                    for t in prop.get("Data", []) or []:
                        tags[t.get("Key")] = t.get("Value")
            arn = r.get("Arn", "")
            resources.append(Resource(
                service=r.get("Service", "?"),
                resource_type=r.get("ResourceType", "?"),
                id=arn.rsplit("/", 1)[-1].rsplit(":", 1)[-1] or arn,
                arn=arn,
                region=r.get("Region"),
                account=r.get("OwningAccountId"),
                name=tags.get("Name"),
                tags=tags,
            ))
        token = resp.get("NextToken")
        pages += 1
        if not token:
            break
    return resources
