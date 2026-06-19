"""boto3 session resolution for the three configured auth modes, plus a retrying client factory.

  profile      -> named profile from ~/.aws
  env          -> standard credential chain (env vars / container role)
  assume_role  -> base creds (env or profile) assume cfg.aws.role_arn via STS
"""
from __future__ import annotations

import boto3
from botocore.config import Config as BotoConfig

from finops_core.config import Config

# Adaptive retries handle Cost Explorer / Bedrock throttling gracefully.
RETRY_CONFIG = BotoConfig(retries={"max_attempts": 10, "mode": "adaptive"})


def _base_session(cfg: Config) -> boto3.Session:
    """Base session used directly (profile/env) or as the principal for assume_role."""
    use_profile = cfg.aws.auth == "profile" or (
        cfg.aws.auth == "assume_role" and cfg.aws.assume_base == "profile"
    )
    if use_profile:
        return boto3.Session(profile_name=cfg.aws.profile, region_name=cfg.aws.region)
    # env mode / container role: rely on the default credential chain
    return boto3.Session(region_name=cfg.aws.region)


def build_session(cfg: Config) -> boto3.Session:
    """Resolve a boto3 Session per cfg.aws.auth."""
    auth = cfg.aws.auth
    if auth in ("profile", "env"):
        return _base_session(cfg)
    if auth == "assume_role":
        if not cfg.aws.role_arn:
            raise ValueError("auth=assume_role requires aws.role_arn (set FINOPS_ROLE_ARN)")
        sts = _base_session(cfg).client("sts", config=RETRY_CONFIG)
        kwargs = {
            "RoleArn": cfg.aws.role_arn,
            "RoleSessionName": cfg.aws.role_session_name,
        }
        if cfg.aws.external_id:
            kwargs["ExternalId"] = cfg.aws.external_id
        creds = sts.assume_role(**kwargs)["Credentials"]
        return boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name=cfg.aws.region,
        )
    raise ValueError(f"unknown aws.auth mode: {auth!r} (expected profile|env|assume_role)")


def client(session: boto3.Session, service: str, region: str | None = None):
    """Service client with adaptive retries; pass region for service-specific endpoints
    (e.g. Cost Explorer must use us-east-1)."""
    return session.client(service, region_name=region, config=RETRY_CONFIG)
