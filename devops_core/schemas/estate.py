"""Normalized estate inventory: one Resource shape across all discovery sources, and an Estate
aggregate. JSON-serializable; the single source of truth for the UI, agent, and diagram.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


def parse_arn(arn: str) -> dict:
    """Best-effort parse of an ARN -> {service, resource_type, region, account, id}.
    Handles arn:partition:service:region:account:type/id and ...:type:id and ...:id and S3."""
    parts = (arn or "").split(":", 5)
    if len(parts) < 6 or parts[0] != "arn":
        return {"service": "?", "resource_type": "?", "region": None, "account": None, "id": arn}
    _, _, service, region, account, resource = parts
    rtype, sep, rid = resource.partition("/")
    if not sep:  # no slash — maybe "type:id" (e.g. lambda function:name)
        rtype2, sep2, rid2 = resource.partition(":")
        if sep2:
            rtype, rid = rtype2, rid2
        else:
            rtype, rid = "", resource  # bare id (e.g. s3 bucket name)
    return {
        "service": service,
        "resource_type": f"{service}:{rtype}" if rtype else service,
        "region": region or None,
        "account": account or None,
        "id": rid or resource,
    }


@dataclass
class Resource:
    service: str
    resource_type: str
    id: str
    arn: Optional[str] = None
    region: Optional[str] = None
    account: Optional[str] = None
    name: Optional[str] = None
    tags: dict = field(default_factory=dict)
    properties: dict = field(default_factory=dict)

    @classmethod
    def from_arn(cls, arn: str, tags: Optional[dict] = None, name: Optional[str] = None,
                 **extra) -> "Resource":
        p = parse_arn(arn)
        return cls(service=p["service"], resource_type=p["resource_type"], id=p["id"], arn=arn,
                   region=p["region"], account=p["account"],
                   name=name or (tags or {}).get("Name"), tags=tags or {}, properties=extra)

    def key(self) -> str:
        return self.arn or f"{self.service}:{self.resource_type}:{self.id}:{self.region}"


@dataclass
class Estate:
    resources: list                       # list[Resource]
    notes: list = field(default_factory=list)
    source: str = ""

    @property
    def accounts(self) -> list:
        return sorted({r.account for r in self.resources if r.account})

    @property
    def regions(self) -> list:
        return sorted({r.region for r in self.resources if r.region})

    def counts(self, attr: str) -> dict:
        out: dict = {}
        for r in self.resources:
            v = getattr(r, attr) or "?"
            out[v] = out.get(v, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def to_dict(self) -> dict:
        return {
            "count": len(self.resources),
            "accounts": self.accounts,
            "regions": self.regions,
            "by_service": self.counts("service"),
            "by_region": self.counts("region"),
            "by_account": self.counts("account"),
            "source": self.source,
            "notes": self.notes,
            "resources": [asdict(r) for r in self.resources],
        }
