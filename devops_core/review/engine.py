"""review_service — dispatch a resource to its reviewer (or a generic fallback).

Infers the service from an ARN when not given, normalizes the resource id the API expects, and
returns a ServiceReview. Read-only throughout.
"""
from __future__ import annotations

from typing import Optional

from devops_core.review import fetch
from devops_core.review.schemas import ServiceReview

_REVIEWERS = {
    "lambda": fetch.review_lambda,
    "ec2": fetch.review_ec2,
    "rds": fetch.review_rds,
    "s3": fetch.review_s3,
}

# Map loose service aliases to a reviewer key.
_ALIASES = {
    "aws lambda": "lambda", "function": "lambda", "functions": "lambda",
    "instance": "ec2", "instances": "ec2", "compute": "ec2",
    "database": "rds", "db": "rds",
    "bucket": "s3", "buckets": "s3",
}


def infer_service(service: str, resource_id: str) -> str:
    """Best-effort service key from the given service string or the ARN."""
    s = (service or "").strip().lower()
    s = _ALIASES.get(s, s)
    if s in _REVIEWERS:
        return s
    if resource_id.startswith("arn:"):
        parts = resource_id.split(":")
        if len(parts) >= 3:
            svc = parts[2].lower()
            return _ALIASES.get(svc, svc)
    if resource_id.startswith("i-"):
        return "ec2"
    return s


def resource_name(service: str, resource_id: str) -> str:
    """The identifier the service API expects, extracted from an ARN when needed.
    (Lambda accepts the ARN directly, so it's passed through.)"""
    if service == "lambda":
        return resource_id
    if resource_id.startswith("arn:"):
        # arn:aws:s3:::bucket | arn:aws:ec2:r:a:instance/i-x | arn:aws:rds:r:a:db:name
        tail = resource_id.split(":", 5)[-1]
        if "/" in tail:
            return tail.split("/", 1)[1]
        if ":" in tail:  # rds 'db:name'
            return tail.split(":", 1)[1]
        return tail
    return resource_id


def review_service(service: str, resource_id: str, region: Optional[str] = None,
                   session=None, cfg=None, include_code: bool = True) -> ServiceReview:
    from finops_core.config import Config
    cfg = cfg or Config.load()
    if session is None:
        from finops_core.aws.session import build_session
        session = build_session(cfg)
    region = region or getattr(getattr(cfg, "aws", None), "region", None)

    svc = infer_service(service, resource_id)
    name = resource_name(svc, resource_id)
    reviewer = _REVIEWERS.get(svc)
    if reviewer is None:
        return ServiceReview(
            svc or "unknown", resource_id, region,
            notes=[f"no dedicated reviewer for {svc or service!r} yet — review the live config "
                   "against the AWS Well-Architected Framework (security, reliability, "
                   "performance, cost, operational excellence)."])
    if svc == "lambda":
        return reviewer(session, region, name, include_code=include_code)
    return reviewer(session, region, name)
