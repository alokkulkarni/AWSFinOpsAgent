"""Amazon S3 best-practice rules — security & data-protection baseline.

`config` is a normalized snapshot: {encryption, public_access_block, versioning, lifecycle, logging}.
"""
from __future__ import annotations

from devops_core.review.schemas import Finding

_DOC = "https://docs.aws.amazon.com/AmazonS3/latest/userguide/"
_PAB_KEYS = ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")


def s3_findings(config: dict, metrics: dict | None = None) -> list:
    out: list[Finding] = []

    if not config.get("encryption"):
        out.append(Finding(
            "s3.encryption.missing", "No default bucket encryption", "high",
            current="none", recommended="SSE-S3 or SSE-KMS default encryption",
            rationale="Default encryption ensures every new object is encrypted at rest without "
                      "relying on per-request headers.", category="security",
            doc_url=_DOC + "default-bucket-encryption.html"))

    pab = config.get("public_access_block") or {}
    if not all(pab.get(k) for k in _PAB_KEYS):
        out.append(Finding(
            "s3.public_access.open", "Block Public Access not fully enabled", "critical",
            current="one or more BPA settings off", recommended="enable all four BPA settings",
            rationale="Full Block Public Access is the primary guardrail against accidental public "
                      "exposure of bucket data.", category="security",
            doc_url=_DOC + "access-control-block-public-access.html"))

    if (config.get("versioning") or "Disabled") != "Enabled":
        out.append(Finding(
            "s3.versioning.disabled", "Versioning disabled", "medium",
            current=config.get("versioning") or "Disabled", recommended="enable versioning",
            rationale="Versioning protects against accidental overwrite/delete and underpins "
                      "replication and object-lock.", category="reliability",
            doc_url=_DOC + "Versioning.html"))

    if not config.get("lifecycle"):
        out.append(Finding(
            "s3.lifecycle.missing", "No lifecycle rules", "low",
            current="none", recommended="add transition/expiration rules",
            rationale="Lifecycle rules cut cost by transitioning cold data to IA/Glacier and "
                      "expiring obsolete objects/old versions.", category="cost",
            doc_url=_DOC + "object-lifecycle-mgmt.html"))

    if not config.get("logging"):
        out.append(Finding(
            "s3.logging.missing", "Server access logging off", "low",
            current="disabled", recommended="enable access logging / CloudTrail data events",
            rationale="Access logs support security investigation and access auditing.",
            category="security", doc_url=_DOC + "ServerLogs.html"))

    return out
