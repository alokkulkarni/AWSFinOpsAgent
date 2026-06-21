"""EstateIndex — a scanned-and-cached Estate with query methods for the DevOps agent/tools.

The estate is scanned once (lazily) and reused for the process. Inject `estate=` for tests.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from devops_core.schemas.estate import Estate


class EstateIndex:
    def __init__(self, session=None, cfg=None, regions: Optional[list] = None,
                 estate: Optional[Estate] = None, fan_out: bool = False,
                 role_name: str = "OrganizationAccountAccessRole"):
        self._session = session
        self._cfg = cfg
        self._regions = regions
        self._estate = estate
        self._fan_out = fan_out
        self._role_name = role_name

    def estate(self) -> Estate:
        if self._estate is None:
            from devops_core.discovery.engine import EstateScanner
            self._estate = EstateScanner(self._session, self._cfg).scan(
                regions=self._regions, fan_out=self._fan_out, role_name=self._role_name)
        return self._estate

    def summary(self) -> dict:
        d = self.estate().to_dict()
        d.pop("resources", None)
        return d

    def list(self, service: Optional[str] = None, resource_type: Optional[str] = None,
             region: Optional[str] = None, account: Optional[str] = None, limit: int = 50) -> dict:
        rs = [
            r for r in self.estate().resources
            if (service is None or r.service == service)
            and (resource_type is None or r.resource_type == resource_type)
            and (region is None or r.region == region)
            and (account is None or r.account == account)
        ]
        return {"count": len(rs), "truncated": len(rs) > limit,
                "resources": [asdict(r) for r in rs[:limit]]}

    def _live_session(self):
        """A boto session for on-demand deep describes (the injected one, or build from cfg)."""
        if self._session is None:
            from finops_core.aws.session import build_session
            from finops_core.config import Config
            self._session = build_session(self._cfg or Config.load())
        return self._session

    def describe(self, query: str, details: bool = True) -> dict:
        match = None
        for r in self.estate().resources:
            if r.arn == query or r.id == query:
                match = r
                break
        if match is None:
            for r in self.estate().resources:  # partial match
                if query and (query in (r.arn or "") or query in r.id):
                    match = r
                    break
        if match is None:
            return {"error": f"no resource matching {query!r}"}

        out = asdict(match)
        if details:  # drill-down: live, service-specific attributes the inventory omits
            from devops_core.discovery.details import resource_details
            try:
                out.update(resource_details(self._live_session(), match))
            except Exception as e:  # never let enrichment break the base answer
                out["note"] = f"detail unavailable: {type(e).__name__}"
        return out

    def find(self, query: str, limit: int = 20) -> dict:
        q = (query or "").lower()
        hits = [
            r for r in self.estate().resources
            if q in (r.id or "").lower() or q in (r.name or "").lower()
            or q in (r.arn or "").lower() or q in r.service.lower()
            or q in r.resource_type.lower()
            or any(q in str(v).lower() for v in r.tags.values())
        ]
        return {"count": len(hits), "resources": [asdict(r) for r in hits[:limit]]}
