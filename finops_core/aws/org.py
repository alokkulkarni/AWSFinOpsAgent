"""AWS Organizations resolver: list linked accounts, map account-id -> name, and assume a
per-account read-only role for deep dives. Degrades gracefully for a single (non-org) account.
"""
from __future__ import annotations

from typing import Optional

from finops_core.aws.session import client
from finops_core.config import Config


class OrgResolver:
    def __init__(self, session=None, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self.session = session
        self._name_map: Optional[dict] = None
        self._accounts: Optional[dict] = None

    def _client(self, service: str, region: Optional[str] = None):
        if self.session is None:
            from finops_core.aws.session import build_session
            self.session = build_session(self.cfg)
        return client(self.session, service, region=region)

    def _current_account(self) -> dict:
        try:
            acct = self._client("sts").get_caller_identity()["Account"]
        except Exception:
            acct = "unknown"
        name = acct
        try:  # account alias is a friendly single-account name
            aliases = self._client("iam").list_account_aliases().get("AccountAliases", [])
            if aliases:
                name = aliases[0]
        except Exception:
            pass
        return {"id": acct, "name": name, "status": "current", "source": "single-account"}

    def list_accounts(self) -> dict:
        """Return {accounts: [...], is_org: bool, note}. Falls back to the current account.
        Cached for the resolver's lifetime (avoids duplicate Organizations calls)."""
        if self._accounts is not None:
            return self._accounts
        accounts, note = [], ""
        try:
            org = self._client("organizations")
            paginator = org.get_paginator("list_accounts")
            for page in paginator.paginate():
                for a in page.get("Accounts", []):
                    accounts.append({"id": a["Id"], "name": a.get("Name", a["Id"]),
                                     "email": a.get("Email"), "status": a.get("Status"),
                                     "source": "organizations"})
            if accounts:
                self._accounts = {"accounts": accounts, "is_org": True, "note": ""}
                return self._accounts
            note = "organization has no listable accounts"
        except Exception as e:
            note = f"not an Organizations management account ({type(e).__name__}) — single-account view"
        self._accounts = {"accounts": [self._current_account()], "is_org": False, "note": note}
        return self._accounts

    def name_map(self) -> dict:
        if self._name_map is None:
            self._name_map = {a["id"]: a["name"] for a in self.list_accounts()["accounts"]}
        return self._name_map

    def label(self, account_id: str) -> str:
        name = self.name_map().get(account_id)
        return f"{account_id} ({name})" if name and name != account_id else account_id

    def enrich_breakdown(self, breakdown: dict) -> dict:
        """Replace LINKED_ACCOUNT group keys (ids) with 'id (name)' labels."""
        names = self.name_map()
        for g in breakdown.get("groups", []):
            key = g.get("key", "")
            if key in names and names[key] != key:
                g["key"] = f"{key} ({names[key]})"
        return breakdown

    def assume_account(self, account_id: str, role_name: str = "FinOpsReadOnly",
                       session_name: str = "finops-fanout"):
        """Return a boto3 Session assuming role_name in account_id (for per-account deep dives)."""
        import boto3
        sts = self._client("sts")
        arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        creds = sts.assume_role(RoleArn=arn, RoleSessionName=session_name)["Credentials"]
        return boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name=self.cfg.aws.region,
        )
