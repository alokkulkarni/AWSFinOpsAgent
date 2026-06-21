"""EstateScanner — orchestrate the discovery sources into a normalized Estate, gracefully.

Per account (auto): Config aggregator (if populated) -> Resource Explorer (per region) ->
Tagging API (per region). With fan_out=True, also assume a read-only role into each
Organization member account and scan it; resources are deduped by ARN/key; every unavailable
source / un-assumable account becomes a note.
"""
from __future__ import annotations

from typing import Optional

from finops_core.aws.org import OrgResolver
from finops_core.aws.session import build_session, client
from finops_core.config import Config
from devops_core.discovery import config_agg, resource_explorer, tagging
from devops_core.schemas.estate import Estate

DEFAULT_MEMBER_ROLE = "OrganizationAccountAccessRole"


def _caller_account(session) -> Optional[str]:
    try:
        return client(session, "sts").get_caller_identity()["Account"]
    except Exception:
        return None


class EstateScanner:
    def __init__(self, session=None, cfg: Optional[Config] = None):
        self.cfg = cfg or Config.load()
        self.session = session or build_session(self.cfg)

    def enabled_regions(self) -> list:
        try:
            ec2 = client(self.session, "ec2", self.cfg.aws.region)
            regions = ec2.describe_regions(Filters=[{"Name": "opt-in-status",
                "Values": ["opt-in-not-required", "opted-in"]}])["Regions"]
            return sorted(r["RegionName"] for r in regions)
        except Exception:
            return [self.cfg.aws.region]

    def _scan_one(self, session, regions: list, source: str):
        """Discover one account's resources (the current `session`). Returns (resources, notes, used)."""
        seen: dict = {}
        notes: list = []
        used: list = []

        if source in ("auto", "config"):
            try:
                agg = config_agg.first_aggregator(session)
                if agg and config_agg.discovered_count(session, agg) > 0:
                    for r in config_agg.list_resources(session, agg):
                        seen[r.key()] = r
                    used.append("config")
                elif agg:
                    notes.append(f"config aggregator '{agg}' has 0 resources (recording not enabled)")
            except Exception as e:
                notes.append(f"config: {type(e).__name__}")

        if source in ("auto", "resource-explorer"):
            for reg in regions:
                try:
                    found = resource_explorer.search(session, reg)
                    for r in found:
                        seen[r.key()] = r
                    if found:
                        used.append("resource-explorer")
                except Exception as e:
                    notes.append(f"resource-explorer {reg}: {type(e).__name__}")

        if source in ("auto", "tagging"):
            for reg in regions:
                try:
                    for r in tagging.get_resources(session, reg):
                        seen.setdefault(r.key(), r)
                    used.append("tagging")
                except Exception as e:
                    notes.append(f"tagging {reg}: {type(e).__name__}")

        return list(seen.values()), notes, used

    def scan(self, regions: Optional[list] = None, source: str = "auto",
             fan_out: bool = False, role_name: str = DEFAULT_MEMBER_ROLE) -> Estate:
        regions = regions or self.enabled_regions()
        seen: dict = {}
        notes: list = []
        used: list = []

        rs, ns, us = self._scan_one(self.session, regions, source)
        for r in rs:
            seen[r.key()] = r
        notes += ns
        used += us

        if fan_out:
            org = OrgResolver(self.session, self.cfg)
            current = _caller_account(self.session)
            try:
                accounts = org.list_accounts().get("accounts", [])
            except Exception as e:
                accounts = []
                notes.append(f"organizations: {type(e).__name__}")
            for acct in accounts:
                if acct["id"] == current:
                    continue
                try:
                    member_session = org.assume_account(acct["id"], role_name)
                    mrs, mns, _mus = self._scan_one(member_session, regions, source)
                    for r in mrs:
                        seen[r.key()] = r
                    notes += [f"{acct['name']}({acct['id']}): {n}" for n in mns]
                    used.append(f"account:{acct['id']}")
                except Exception as e:
                    notes.append(f"account {acct['id']} ({acct.get('name', '?')}): "
                                 f"cannot assume {role_name} ({type(e).__name__})")

        if not seen:
            notes.append("no resources discovered — check Resource Explorer / tag:GetResources access")
        return Estate(resources=list(seen.values()), notes=notes,
                      source=",".join(sorted(set(used))) or "none")
