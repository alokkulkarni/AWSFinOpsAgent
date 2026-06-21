"""Resource Groups Tagging API source — tagged resources (with tags) per region."""
from __future__ import annotations

from finops_core.aws.session import client
from devops_core.schemas.estate import Resource


def get_resources(session, region: str, max_pages: int = 30) -> list:
    tag = client(session, "resourcegroupstaggingapi", region=region)
    out: list = []
    token, pages = None, 0
    while pages < max_pages:
        kwargs = {"ResourcesPerPage": 100}
        if token:
            kwargs["PaginationToken"] = token
        resp = tag.get_resources(**kwargs)
        for m in resp.get("ResourceTagMappingList", []):
            tags = {t["Key"]: t["Value"] for t in m.get("Tags", [])}
            out.append(Resource.from_arn(m["ResourceARN"], tags=tags))
        token = resp.get("PaginationToken")
        pages += 1
        if not token:
            break
    return out
