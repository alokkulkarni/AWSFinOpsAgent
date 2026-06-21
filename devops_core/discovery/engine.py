"""EstateScanner — orchestrate the discovery sources into a normalized Estate, gracefully.

Order (auto): Config aggregator (if populated) -> Resource Explorer (per region) -> Tagging API
(per region). Resources are deduped by ARN/key; every unavailable source becomes a note.
"""
from __future__ import annotations

from typing import Optional

from finops_core.aws.session import build_session, client
from finops_core.config import Config
from devops_core.discovery import config_agg, resource_explorer, tagging
from devops_core.schemas.estate import Estate


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

    def scan(self, regions: Optional[list] = None, source: str = "auto") -> Estate:
        regions = regions or self.enabled_regions()
        seen: dict = {}
        notes: list = []
        used: list = []

        # 1) Config aggregator (org-wide, richest) — only if it actually has resources
        if source in ("auto", "config"):
            try:
                agg = config_agg.first_aggregator(self.session)
                if agg and config_agg.discovered_count(self.session, agg) > 0:
                    for r in config_agg.list_resources(self.session, agg):
                        seen[r.key()] = r
                    used.append("config")
                elif agg:
                    notes.append(f"config aggregator '{agg}' has 0 resources (recording not enabled)")
                else:
                    notes.append("no Config aggregator configured")
            except Exception as e:
                notes.append(f"config: {type(e).__name__}")

        # 2) Resource Explorer (broad, per region)
        if source in ("auto", "resource-explorer"):
            for reg in regions:
                try:
                    found = resource_explorer.search(self.session, reg)
                    for r in found:
                        seen[r.key()] = r
                    if found:
                        used.append("resource-explorer")
                except Exception as e:
                    notes.append(f"resource-explorer {reg}: {type(e).__name__}")

        # 3) Tagging API (supplement: adds tagged resources + tags)
        if source in ("auto", "tagging"):
            for reg in regions:
                try:
                    for r in tagging.get_resources(self.session, reg):
                        seen.setdefault(r.key(), r)
                    used.append("tagging")
                except Exception as e:
                    notes.append(f"tagging {reg}: {type(e).__name__}")

        if not seen:
            notes.append("no resources discovered — check Resource Explorer index / "
                         "tag:GetResources permissions in the scanned regions")
        return Estate(resources=list(seen.values()), notes=notes,
                      source=",".join(sorted(set(used))) or "none")
