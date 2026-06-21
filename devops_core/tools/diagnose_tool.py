"""`diagnose_service` tool — fault debugging for the DevOps agent.

Read-only diagnosis (config + CloudWatch alarms + recent Logs errors + recent CloudTrail changes)
→ ranked root-cause hypotheses + fixes. The fix output is shaped by the action posture (the mode):
advisory hides apply commands; artifacts include them; guarded_write marks them confirmation-gated.
Named diagnose_* (not a write prefix) so the ReadOnlyGuard never blocks the read-only diagnosis.
"""
from __future__ import annotations


def build_diagnose_tools(session=None, cfg=None):
    from strands import tool

    @tool
    def diagnose_service(service: str, resource_id: str, region: str = "") -> dict:
        """Debug a faulty/misbehaving AWS resource: validate its current state (config + CloudWatch
        alarms + recent error logs + recent CloudTrail changes), correlate into ranked ROOT-CAUSE
        hypotheses with evidence, and propose fixes. Read-only diagnosis.

        Best signal for Lambda (reads its log group); EC2/RDS/others use alarms + CloudTrail.
        `service`: e.g. 'lambda' | 'ec2' | 'rds' (inferred from an ARN if blank).
        `resource_id`: name, id, or ARN. Use for "why is X failing / erroring / timing out / down".
        Apply commands appear only in artifacts/guarded_write mode (guarded requires confirmation)."""
        from devops_core.diagnose.engine import diagnose_service as _diag
        return _diag(service, resource_id, region or None, session=session, cfg=cfg).to_dict()

    return [diagnose_service]
