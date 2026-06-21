"""`review_service` tool — per-service best-practice review for the DevOps agent.

Read-only. Returns deterministic, AWS-doc-cited findings (top-N) the LLM prioritizes/narrates.
Named review_* (not a write prefix) so the ReadOnlyGuard never blocks it.
"""
from __future__ import annotations


def build_review_tools(session=None, cfg=None, limit: int = 12):
    from strands import tool

    @tool
    def review_service(service: str, resource_id: str, region: str = "") -> dict:
        """Review one AWS resource for optimizations and return prioritized, AWS-doc-cited findings
        across security / reliability / performance / cost / sizing — from live config + CloudWatch
        metrics (and, for Lambda, the deployed code).

        Deep reviewers: lambda, ec2, rds, s3 (other services get a Well-Architected note).
        `service`: e.g. 'lambda' | 'ec2' | 'rds' | 's3' (inferred from an ARN if blank).
        `resource_id`: name, id, or ARN. `region`: optional override.
        Use for "review/optimize my <service> <name>", "is this bucket secure", "tune this lambda"."""
        from devops_core.review.engine import review_service as _review
        return _review(service, resource_id, region or None, session, cfg).to_dict(limit=limit)

    return [review_service]
