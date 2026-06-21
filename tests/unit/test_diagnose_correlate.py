"""Fault correlation — pure rules over gathered signals → ranked root-cause hypotheses.
Plus posture-shaped output (advisory hides apply commands; guarded_write requires confirmation)."""
from devops_core.diagnose.correlate import correlate
from devops_core.diagnose.schemas import Diagnosis


def _causes(hyps):
    return {h.cause for h in hyps}


def test_lambda_timeout_from_logs():
    hyps = correlate("lambda", {"Timeout": 3}, {
        "log_errors": ["2026-06-21 Task timed out after 3.00 seconds"],
        "alarms": [], "recent_changes": []})
    assert any("timing out" in c.lower() or "timeout" in c.lower() for c in _causes(hyps))
    assert all(h.fix for h in hyps)


def test_lambda_import_error_from_logs():
    hyps = correlate("lambda", {}, {
        "log_errors": ["[ERROR] Runtime.ImportModuleError: Unable to import module 'app'"],
        "alarms": [], "recent_changes": []})
    assert any("import" in c.lower() or "dependency" in c.lower() or "handler" in c.lower()
               for c in _causes(hyps))


def test_throttle_alarm_concurrency():
    hyps = correlate("lambda", {}, {
        "log_errors": [], "recent_changes": [],
        "alarms": [{"name": "fn-throttles", "metric": "Throttles", "state": "ALARM"}]})
    assert any("concurrenc" in c.lower() or "throttl" in c.lower() for c in _causes(hyps))


def test_recent_change_correlated_when_faulting():
    hyps = correlate("lambda", {"Timeout": 3}, {
        "log_errors": ["Task timed out after 3.00 seconds"], "alarms": [],
        "recent_changes": [{"event": "UpdateFunctionConfiguration", "user": "ci", "time": "t"}]})
    assert any("recent change" in c.lower() or "change" in c.lower() for c in _causes(hyps))


def test_healthy_when_no_signals():
    hyps = correlate("lambda", {}, {"log_errors": [], "alarms": [], "recent_changes": []})
    assert hyps == []


def test_mode_shapes_fix_command_visibility():
    d = Diagnosis("lambda", "f", "eu-west-2", mode="advisory", hypotheses=correlate(
        "lambda", {"Timeout": 3}, {"log_errors": ["Task timed out after 3.00 seconds"],
                                   "alarms": [], "recent_changes": []}))
    # advisory: no apply command leaks
    assert all("fix_command" not in h for h in d.to_dict()["hypotheses"])
    # guarded_write: command present but gated behind confirmation
    d.mode = "guarded_write"
    gh = d.to_dict()["hypotheses"]
    assert any(h.get("apply", "").startswith("guarded_write") for h in gh if h.get("fix_command"))
