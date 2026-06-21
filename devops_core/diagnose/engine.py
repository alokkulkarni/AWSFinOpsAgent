"""diagnose_service — gather signals → correlate → posture-shaped Diagnosis. Read-only."""
from __future__ import annotations

from typing import Optional

from devops_core.diagnose import signals as sig
from devops_core.diagnose.correlate import correlate
from devops_core.diagnose.schemas import Diagnosis
from devops_core.review.engine import infer_service, resource_name


def _light_config(svc: str, session, region: str, name: str) -> tuple[dict, list]:
    """Minimal config needed by correlation (e.g. Lambda Timeout). Graceful."""
    from finops_core.aws.session import client
    try:
        if svc == "lambda":
            c = client(session, "lambda", region).get_function_configuration(FunctionName=name)
            return {k: c.get(k) for k in ("Runtime", "Timeout", "MemorySize", "Handler")}, []
    except Exception as e:
        return {}, [f"config: {type(e).__name__}"]
    return {}, []


def diagnose_service(service: str, resource_id: str, region: Optional[str] = None,
                     mode: Optional[str] = None, session=None, cfg=None) -> Diagnosis:
    from finops_core.config import Config
    from finops_core.modes import normalize_mode
    cfg = cfg or Config.load()
    if session is None:
        from finops_core.aws.session import build_session
        session = build_session(cfg)
    region = region or getattr(getattr(cfg, "aws", None), "region", None)
    mode = normalize_mode(mode or getattr(cfg, "mode", "advisory"))

    svc = infer_service(service, resource_id)
    name = sig.lambda_name(resource_id) if svc == "lambda" else resource_name(svc, resource_id)

    config, notes = _light_config(svc, session, region, name)
    signals = {
        "config": config,
        "alarms": sig.active_alarms(session, region, name),
        "log_errors": sig.recent_log_errors(session, region, svc, name),
        "recent_changes": sig.recent_changes(session, region, name),
    }
    hyps = correlate(svc, config, signals)
    if not (signals["alarms"] or signals["log_errors"] or signals["recent_changes"]):
        notes.append("No active alarms, recent error logs, or recent changes found — "
                     "no active fault detected in the inspected window.")
    if svc != "lambda" and not signals["alarms"]:
        notes.append(f"Log-based diagnosis is Lambda-only so far; for {svc} this relies on "
                     "CloudWatch alarms + CloudTrail.")
    return Diagnosis(svc, resource_id, region, mode, signals=signals, hypotheses=hyps, notes=notes)
