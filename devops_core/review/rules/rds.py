"""Amazon RDS best-practice rules — security, reliability, cost."""
from __future__ import annotations

from devops_core.review.schemas import Finding

_DOC = "https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/"
_PREV_GEN = ("db.t2.", "db.m1.", "db.m2.", "db.m3.", "db.m4.", "db.r3.", "db.r4.")


def rds_findings(config: dict, metrics: dict | None = None) -> list:
    out: list[Finding] = []

    if config.get("PubliclyAccessible"):
        out.append(Finding(
            "rds.public", "Database is publicly accessible", "critical",
            current="PubliclyAccessible=true", recommended="private subnets only; false",
            rationale="A public database is reachable from the internet — a major exposure even "
                      "behind a security group. Keep it private.",
            category="security", doc_url=_DOC + "USER_VPC.WorkingWithRDSInstanceinaVPC.html"))

    if config.get("StorageEncrypted") is False:
        out.append(Finding(
            "rds.encryption.disabled", "Storage not encrypted at rest", "critical",
            current="StorageEncrypted=false", recommended="enable KMS encryption",
            rationale="Encryption at rest is a baseline control (and often a compliance "
                      "requirement); it must be set at/with a snapshot restore.",
            category="security", doc_url=_DOC + "Overview.Encryption.html"))

    if config.get("MultiAZ") is False:
        out.append(Finding(
            "rds.multiaz.disabled", "Single-AZ deployment", "high",
            current="MultiAZ=false", recommended="Multi-AZ for production",
            rationale="Multi-AZ provides automatic failover; single-AZ risks downtime/data loss "
                      "on an AZ or instance failure.", category="reliability",
            doc_url=_DOC + "Concepts.MultiAZ.html"))

    if config.get("BackupRetentionPeriod") == 0:
        out.append(Finding(
            "rds.backups.disabled", "Automated backups disabled", "high",
            current="retention=0 days", recommended=">= 7 days",
            rationale="Retention 0 disables automated backups and point-in-time recovery.",
            category="reliability", doc_url=_DOC + "USER_WorkingWithAutomatedBackups.html"))

    if config.get("StorageType") == "gp2":
        out.append(Finding(
            "rds.storage.gp3", "Using gp2 storage", "low",
            current="gp2", recommended="gp3",
            rationale="gp3 decouples IOPS/throughput from size and is generally cheaper per GB.",
            category="cost", doc_url=_DOC + "CHAP_Storage.html"))

    if config.get("PerformanceInsightsEnabled") is False:
        out.append(Finding(
            "rds.perf_insights.off", "Performance Insights disabled", "low",
            current="disabled", recommended="enable Performance Insights",
            rationale="Performance Insights makes DB load and top SQL/ waits visible for tuning.",
            category="performance", doc_url=_DOC + "USER_PerfInsights.html"))

    cls = config.get("DBInstanceClass") or ""
    if cls.startswith(_PREV_GEN):
        out.append(Finding(
            "rds.gen.previous", "Previous-generation instance class", "medium",
            current=cls, recommended="current gen (e.g. db.m7g/db.r7g Graviton)",
            rationale="Newer/Graviton classes give better price-performance.",
            category="cost", doc_url=_DOC + "Concepts.DBInstanceClass.html"))

    return out
