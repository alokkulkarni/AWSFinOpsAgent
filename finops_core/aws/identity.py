"""Caller identity (STS) and account-id redaction helpers."""
from __future__ import annotations

import re

import boto3

from finops_core.aws.session import client

_ACCOUNT_RE = re.compile(r"\d{12}")


def get_caller_identity(session: boto3.Session) -> dict:
    """Return {account, arn, user_id} for the resolved credentials (read-only, free)."""
    r = client(session, "sts").get_caller_identity()
    return {"account": r["Account"], "arn": r["Arn"], "user_id": r["UserId"]}


def redact_account(account: str, redact: bool = True) -> str:
    if not redact or not account:
        return account
    return f"{account[:4]}****{account[-2:]}" if len(account) >= 6 else "****"


def redact_arn(arn: str, redact: bool = True) -> str:
    if not redact or not arn:
        return arn
    return _ACCOUNT_RE.sub("************", arn)
