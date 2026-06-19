from unittest.mock import MagicMock

import boto3
from botocore.stub import Stubber

from finops_core.aws.org import OrgResolver


def test_list_accounts_organization(monkeypatch):
    org = boto3.client("organizations", region_name="us-east-1",
                       aws_access_key_id="x", aws_secret_access_key="y", aws_session_token="z")
    stub = Stubber(org)
    stub.add_response("list_accounts", {"Accounts": [
        {"Id": "111111111111", "Name": "prod", "Email": "a@b.com", "Status": "ACTIVE"},
        {"Id": "222222222222", "Name": "dev", "Email": "c@d.com", "Status": "ACTIVE"},
    ]})
    stub.activate()

    r = OrgResolver()
    monkeypatch.setattr(r, "_client", lambda service, region=None: org)
    data = r.list_accounts()

    assert data["is_org"] is True
    assert {a["id"] for a in data["accounts"]} == {"111111111111", "222222222222"}
    assert r.name_map()["111111111111"] == "prod"


def test_list_accounts_single_account_fallback(monkeypatch):
    def fake_client(service, region=None):
        if service == "organizations":
            raise RuntimeError("AWSOrganizationsNotInUseException")
        m = MagicMock()
        if service == "sts":
            m.get_caller_identity.return_value = {"Account": "395402194296"}
        if service == "iam":
            m.list_account_aliases.return_value = {"AccountAliases": ["my-alias"]}
        return m

    r = OrgResolver()
    monkeypatch.setattr(r, "_client", fake_client)
    data = r.list_accounts()

    assert data["is_org"] is False
    assert data["accounts"][0]["id"] == "395402194296"
    assert data["accounts"][0]["name"] == "my-alias"
    assert "single-account" in data["note"] or data["note"]


def test_enrich_breakdown_maps_names():
    r = OrgResolver()
    r._name_map = {"111111111111": "prod"}
    b = {"groups": [{"key": "111111111111", "amount": 10}, {"key": "999", "amount": 5}]}
    r.enrich_breakdown(b)
    assert b["groups"][0]["key"] == "111111111111 (prod)"
    assert b["groups"][1]["key"] == "999"
