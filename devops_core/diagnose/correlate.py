"""Correlate gathered signals into ranked root-cause hypotheses (pure — no AWS).

`signals` = {"log_errors": [str], "alarms": [{name,metric,state}], "recent_changes": [{event,..}]}.
Rules are intentionally conservative and evidence-linked; the LLM narrates/prioritizes on top.
"""
from __future__ import annotations

from devops_core.diagnose.schemas import Hypothesis

_LDOC = "https://docs.aws.amazon.com/lambda/latest/operatorguide/"


def _alarm_metrics(alarms) -> set:
    return {(a.get("metric") or "").lower() for a in (alarms or []) if a.get("state") == "ALARM"}


def _logs_match(log_errors, *needles) -> list:
    out = []
    for line in log_errors or []:
        low = line.lower()
        if any(n.lower() in low for n in needles):
            out.append(line.strip()[:200])
    return out


def correlate(service: str, config: dict, signals: dict) -> list:
    service = (service or "").lower()
    config = config or {}
    logs = signals.get("log_errors") or []
    alarms = signals.get("alarms") or []
    changes = signals.get("recent_changes") or []
    alarmed = _alarm_metrics(alarms)
    hyps: list[Hypothesis] = []

    if service == "lambda":
        hit = _logs_match(logs, "Task timed out")
        if hit:
            to = config.get("Timeout")
            hyps.append(Hypothesis(
                cause="Function is timing out", confidence="high", evidence=hit,
                fix="Raise the timeout or optimize the slow path (downstream calls, cold-start, "
                    "memory→CPU). Profile with X-Ray.",
                fix_command=(f"aws lambda update-function-configuration --function-name <name> "
                             f"--timeout {min((to or 30) * 2, 900)}"),
                category="reliability", doc_url=_LDOC + "monitoring.html"))

        hit = _logs_match(logs, "ImportModuleError", "Unable to import module",
                          "Cannot find module", "MODULE_NOT_FOUND")
        if hit:
            hyps.append(Hypothesis(
                cause="Handler/dependency import failure", confidence="high", evidence=hit,
                fix="Verify the Handler path matches the file/function, and that all dependencies "
                    "are packaged (or in a layer) for the target architecture.",
                category="config", doc_url=_LDOC + "configuration-function-zip.html"))

        hit = _logs_match(logs, "AccessDenied", "not authorized", "AccessDeniedException")
        if hit:
            hyps.append(Hypothesis(
                cause="Permission denied (execution-role IAM)", confidence="high", evidence=hit,
                fix="Add the missing action/resource to the function's execution role policy.",
                category="security", doc_url=_LDOC + "permissions.html"))

        throttle_logs = _logs_match(logs, "Rate Exceeded", "TooManyRequests", "throttl")
        if "throttles" in alarmed or throttle_logs:
            hyps.append(Hypothesis(
                cause="Concurrency throttling", confidence="high",
                evidence=(throttle_logs or ["CloudWatch Throttles alarm in ALARM"]),
                fix="Raise reserved/provisioned concurrency or request an account concurrency "
                    "quota increase; check for a downstream bottleneck.",
                fix_command="aws lambda put-function-concurrency --function-name <name> "
                            "--reserved-concurrent-executions <N>",
                category="reliability", doc_url=_LDOC + "scaling-concurrency.html"))

        oom = _logs_match(logs, "Runtime exited", "out of memory", "OutOfMemory")
        if oom:
            hyps.append(Hypothesis(
                cause="Out-of-memory / runtime crash", confidence="medium", evidence=oom,
                fix="Increase MemorySize (also raises CPU) and check for leaks/large payloads.",
                fix_command="aws lambda update-function-configuration --function-name <name> "
                            "--memory-size <MB>",
                category="reliability", doc_url=_LDOC + "computing-power.html"))

        generic = _logs_match(logs, "[ERROR]", "Traceback", "Exception", "errorMessage")
        if generic and not hyps:
            hyps.append(Hypothesis(
                cause="Unhandled errors in invocations", confidence="medium", evidence=generic[:3],
                fix="Inspect the CloudWatch Logs stack traces; add error handling and an on-failure "
                    "destination/DLQ.", category="reliability", doc_url=_LDOC + "monitoring.html"))

    # service-agnostic: an active alarm with no matched pattern above
    if "errors" in alarmed and not any(h.category == "reliability" for h in hyps):
        hyps.append(Hypothesis(
            cause="Error-rate alarm active", confidence="medium",
            evidence=["CloudWatch Errors alarm in ALARM"],
            fix="Inspect recent logs for the failing path.", category="reliability"))

    if "statuscheckfailed" in alarmed:
        hyps.append(Hypothesis(
            cause="EC2 status check failing (impaired instance)", confidence="high",
            evidence=["StatusCheckFailed alarm in ALARM"],
            fix="Stop/start to migrate to healthy hardware, or replace via the ASG.",
            fix_command="aws ec2 reboot-instances --instance-ids <id>",
            category="reliability"))

    if "freestoragespace" in alarmed:
        hyps.append(Hypothesis(
            cause="RDS storage nearly full", confidence="high",
            evidence=["FreeStorageSpace alarm in ALARM"],
            fix="Increase AllocatedStorage (or enable storage autoscaling); reclaim space.",
            fix_command="aws rds modify-db-instance --db-instance-identifier <id> "
                        "--allocated-storage <GB> --apply-immediately",
            category="reliability"))

    # if a fault was found AND there were recent changes, surface the likely trigger
    if hyps and changes:
        ev = [f"{c.get('event')} by {c.get('user')} @ {c.get('time')}" for c in changes[:3]]
        hyps.append(Hypothesis(
            cause="A recent change may have introduced the fault", confidence="medium",
            evidence=ev,
            fix="Correlate the fault's onset with these CloudTrail changes; roll back the "
                "suspect change if the timing lines up.",
            category="reliability",
            doc_url="https://docs.aws.amazon.com/awscloudtrail/latest/userguide/"))

    return hyps
