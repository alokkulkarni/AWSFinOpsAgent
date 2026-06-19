from pathlib import Path
from unittest.mock import MagicMock

import pytest

from finops_core.config import Config
from finops_core.remediation import audit
from finops_core.remediation.actions import ModeError, RemediationEngine
from finops_core.remediation.artifacts import generate_artifact


# ---- artifacts (deterministic, no AWS) ------------------------------------
def test_artifact_terminate_and_modify():
    a = generate_artifact({"action": "terminate", "resource_id": "i-1", "region": "us-east-1"})
    assert "terminate-instances" in a.content and a.format == "cli"
    m = generate_artifact({"action": "modify", "resource_id": "i-2", "recommended": "m5.large"})
    assert "modify-instance-attribute" in m.content and "m5.large" in m.content


def test_artifact_terraform_budget():
    a = generate_artifact({"action": "create_or_update_budget"}, fmt="terraform")
    assert a.format == "terraform" and "aws_budgets_budget" in a.content


# ---- mode gating ----------------------------------------------------------
def test_preview_requires_guarded_write():
    cfg = Config()  # advisory by default
    with pytest.raises(ModeError):
        RemediationEngine(cfg).preview("create_anomaly_monitor")


def test_list_actions_available_in_any_mode():
    ids = {a.action_id for a in RemediationEngine(Config()).list_actions()}
    assert "create_anomaly_monitor" in ids and "delete_ebs_snapshot" in ids


# ---- token flow + apply + audit (mocked client) ---------------------------
@pytest.fixture
def audit_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "_AUDIT_DIR", tmp_path)
    monkeypatch.setattr(audit, "_AUDIT_LOG", tmp_path / "audit.jsonl")
    monkeypatch.setattr(audit, "_PENDING", tmp_path / "pending.json")
    return tmp_path


def test_guarded_apply_flow(audit_tmp, monkeypatch):
    cfg = Config()
    cfg.mode = "guarded_write"
    eng = RemediationEngine(cfg)
    mock_ce = MagicMock()
    mock_ce.create_anomaly_monitor.return_value = {"MonitorArn": "arn:aws:ce::123:anomalymonitor/x"}
    monkeypatch.setattr(eng, "_client", lambda service, region=None: mock_ce)

    spec = eng.preview("create_anomaly_monitor", {"name": "t"})
    assert spec.confirmation_token

    # wrong token rejected
    assert eng.apply("create_anomaly_monitor", "bogus").status == "rejected"

    # correct token applies + audits + calls AWS once
    res = eng.apply("create_anomaly_monitor", spec.confirmation_token)
    assert res.status == "applied" and "arn:" in res.detail and res.audit_id
    mock_ce.create_anomaly_monitor.assert_called_once()
    assert (audit_tmp / "audit.jsonl").exists()

    # token is single-use
    assert eng.apply("create_anomaly_monitor", spec.confirmation_token).status == "rejected"
