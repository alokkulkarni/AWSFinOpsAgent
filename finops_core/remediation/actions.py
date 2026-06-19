"""Guarded-write actions: an allowlist of low-blast-radius changes, each requiring
guarded_write mode + a single-use confirmation token (the LLM cannot self-approve) + an audit
entry. No IAM/networking/data-plane deletes in v1.
"""
from __future__ import annotations

import uuid
from typing import Optional

from finops_core.aws.session import client
from finops_core.config import Config
from finops_core.remediation import audit
from finops_core.schemas.remediation import ActionResult, ActionSpec


class ModeError(PermissionError):
    pass


def _preview_create_anomaly_monitor(eng, p):
    return f"Create a DIMENSIONAL (SERVICE) cost anomaly monitor named '{p.get('name', 'finops-monitor')}'."


def _apply_create_anomaly_monitor(eng, p):
    ce = eng._client("ce", eng.cfg.aws.ce_region)
    arn = ce.create_anomaly_monitor(AnomalyMonitor={
        "MonitorName": p.get("name", "finops-monitor"),
        "MonitorType": "DIMENSIONAL", "MonitorDimension": "SERVICE",
    })["MonitorArn"]
    return f"created anomaly monitor {arn}"


def _preview_create_budget(eng, p):
    return f"Create/replace a MONTHLY cost budget '{p.get('name', 'finops-monthly')}' at ${p.get('limit', 100)} USD."


def _apply_create_budget(eng, p):
    bud = eng._client("budgets", "us-east-1")
    bud.create_budget(AccountId=eng._account(), Budget={
        "BudgetName": p.get("name", "finops-monthly"),
        "BudgetLimit": {"Amount": str(p.get("limit", 100)), "Unit": "USD"},
        "TimeUnit": "MONTHLY", "BudgetType": "COST",
    })
    return f"created budget {p.get('name', 'finops-monthly')} at ${p.get('limit', 100)}/mo"


def _preview_enable_compute_optimizer(eng, p):
    return "Enroll this account in AWS Compute Optimizer (status=Active)."


def _apply_enable_compute_optimizer(eng, p):
    co = eng._client("compute-optimizer", eng.cfg.aws.region)
    co.update_enrollment_status(status="Active")
    return "Compute Optimizer enrollment set to Active"


def _preview_enable_coh(eng, p):
    return "Enroll this account in AWS Cost Optimization Hub (status=Active)."


def _apply_enable_coh(eng, p):
    coh = eng._client("cost-optimization-hub", "us-east-1")
    coh.update_enrollment_status(status="Active")
    return "Cost Optimization Hub enrollment set to Active"


def _preview_delete_snapshot(eng, p):
    return f"Delete EBS snapshot {p.get('snapshot_id')} (irreversible)."


def _apply_delete_snapshot(eng, p):
    ec2 = eng._client("ec2", eng.cfg.aws.region)
    ec2.delete_snapshot(SnapshotId=p["snapshot_id"])
    return f"deleted snapshot {p['snapshot_id']}"


def _preview_release_eip(eng, p):
    return f"Release unassociated Elastic IP {p.get('allocation_id')}."


def _apply_release_eip(eng, p):
    ec2 = eng._client("ec2", eng.cfg.aws.region)
    ec2.release_address(AllocationId=p["allocation_id"])
    return f"released EIP {p['allocation_id']}"


# action_id -> (title, risk, preview_fn, apply_fn)
ALLOWLIST = {
    "create_anomaly_monitor": ("Create cost anomaly monitor", "low",
                               _preview_create_anomaly_monitor, _apply_create_anomaly_monitor),
    "create_or_update_budget": ("Create/update monthly budget", "low",
                                _preview_create_budget, _apply_create_budget),
    "enable_compute_optimizer": ("Enable Compute Optimizer", "low",
                                 _preview_enable_compute_optimizer, _apply_enable_compute_optimizer),
    "enable_cost_optimization_hub": ("Enable Cost Optimization Hub", "low",
                                     _preview_enable_coh, _apply_enable_coh),
    "delete_ebs_snapshot": ("Delete EBS snapshot", "high",
                            _preview_delete_snapshot, _apply_delete_snapshot),
    "release_unassociated_eip": ("Release unassociated Elastic IP", "medium",
                                 _preview_release_eip, _apply_release_eip),
}


class RemediationEngine:
    def __init__(self, cfg: Optional[Config] = None, session=None):
        self.cfg = cfg or Config.load()
        self.session = session

    def _client(self, service: str, region: Optional[str] = None):
        if self.session is None:
            from finops_core.aws.session import build_session
            self.session = build_session(self.cfg)
        return client(self.session, service, region=region)

    def _account(self) -> str:
        return self._client("sts").get_caller_identity()["Account"]

    def _require_guarded(self):
        if self.cfg.mode != "guarded_write":
            raise ModeError(f"guarded actions require FINOPS_MODE=guarded_write (current: {self.cfg.mode})")

    def list_actions(self) -> list[ActionSpec]:
        return [ActionSpec(aid, meta[0], meta[1]) for aid, meta in ALLOWLIST.items()]

    def preview(self, action_id: str, params: Optional[dict] = None) -> ActionSpec:
        self._require_guarded()
        if action_id not in ALLOWLIST:
            raise ValueError(f"unknown action: {action_id}")
        params = params or {}
        title, risk, preview_fn, _ = ALLOWLIST[action_id]
        token = uuid.uuid4().hex
        audit.mint_token(action_id, params, token)
        return ActionSpec(action_id, title, risk, params, preview_fn(self, params), token)

    def apply(self, action_id: str, token: str, params: Optional[dict] = None) -> ActionResult:
        self._require_guarded()
        if action_id not in ALLOWLIST:
            return ActionResult(action_id, "rejected", "unknown action")
        stored = audit.consume_token(token, action_id)
        if stored is None:
            return ActionResult(action_id, "rejected", "invalid or already-used confirmation token")
        params = params or stored
        _, _, _, apply_fn = ALLOWLIST[action_id]
        try:
            detail = apply_fn(self, params)
            audit_id = audit.record(action_id, params, "applied", detail)
            return ActionResult(action_id, "applied", detail, audit_id)
        except Exception as e:
            audit_id = audit.record(action_id, params, "error", str(e))
            return ActionResult(action_id, "error", str(e), audit_id)
