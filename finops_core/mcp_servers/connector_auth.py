"""Per-request AWS credential injection for MCP connector mode (HTTP header auth).

When the MCP tool servers run as public connectors, users pass their own AWS
credentials via HTTP request headers rather than relying on server-side profiles.

Headers recognised:
  X-Aws-Access-Key-Id      – AWS access key ID (required for connector mode)
  X-Aws-Secret-Access-Key  – AWS secret access key (required for connector mode)
  X-Aws-Session-Token      – session token (optional; for STS / assumed-role creds)
  X-Aws-Region             – region override (optional; falls back to cfg.aws.region)

Priority:
  1. X-Aws-* headers from the HTTP request  →  new boto3.Session per request
  2. No headers (stdio transport / local dev)  →  build_session(cfg)  (server-side creds)

Both paths are transparent to the tool functions: they call session_from_context()
and get back a ready boto3.Session regardless of where the credentials came from.
"""
from __future__ import annotations

import hashlib

import boto3

from finops_core.aws.session import build_session
from finops_core.config import Config


def session_from_context(ctx, cfg: Config) -> boto3.Session:
    """Return a boto3 Session for this MCP request.

    Reads X-Aws-* headers from the HTTP request when available (connector mode);
    falls back to build_session(cfg) for stdio / server-side-credential mode.
    """
    try:
        req = ctx.request_context.request       # Starlette Request; None in stdio
        if req is not None:
            ak = req.headers.get("x-aws-access-key-id", "")
            sk = req.headers.get("x-aws-secret-access-key", "")
            if ak and sk:
                return boto3.Session(
                    aws_access_key_id=ak,
                    aws_secret_access_key=sk,
                    aws_session_token=req.headers.get("x-aws-session-token") or None,
                    region_name=req.headers.get("x-aws-region") or cfg.aws.region,
                )
    except (AttributeError, LookupError):
        pass
    return build_session(cfg)


def cred_key_from_context(ctx, cfg: Config) -> str:
    """Return a stable, hashed key for caching per-user resources (e.g. EstateIndex).

    Returns a 16-hex-char SHA-256 fingerprint of the header credentials when they
    are present, or the sentinel "server-side" when falling back to server creds.
    The raw credential values are never retained.
    """
    try:
        req = ctx.request_context.request
        if req is not None:
            ak = req.headers.get("x-aws-access-key-id", "")
            sk = req.headers.get("x-aws-secret-access-key", "")
            if ak and sk:
                st = req.headers.get("x-aws-session-token", "")
                region = req.headers.get("x-aws-region", "") or cfg.aws.region
                digest = hashlib.sha256(f"{ak}:{sk}:{st}:{region}".encode()).hexdigest()
                return digest[:16]
    except (AttributeError, LookupError):
        pass
    return "server-side"
