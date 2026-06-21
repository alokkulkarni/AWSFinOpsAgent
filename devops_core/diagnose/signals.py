"""Gather live fault signals (read-only, all graceful → [] on failure):
CloudWatch alarms in ALARM, recent Logs error lines, and recent mutating CloudTrail changes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from finops_core.aws.session import client

_LOG_FILTER = ('?ERROR ?Exception ?Traceback ?"Task timed out" ?ImportModuleError '
               '?"Rate Exceeded" ?AccessDenied ?"Runtime exited"')


def lambda_name(resource_id: str) -> str:
    """Function name from a name or ARN (arn:aws:lambda:r:a:function:NAME[:qual])."""
    if ":function:" in resource_id:
        return resource_id.split(":function:", 1)[1].split(":", 1)[0]
    return resource_id


def active_alarms(session, region: str, dim_value: str) -> list:
    """CloudWatch alarms in ALARM whose dimensions reference the resource."""
    try:
        cw = client(session, "cloudwatch", region)
        out = []
        token = None
        while True:
            kw = {"StateValue": "ALARM", "MaxRecords": 100}
            if token:
                kw["NextToken"] = token
            resp = cw.describe_alarms(**kw)
            for a in resp.get("MetricAlarms", []):
                if any(dim_value == d.get("Value") for d in a.get("Dimensions", [])):
                    out.append({"name": a.get("AlarmName"), "metric": a.get("MetricName"),
                                "state": a.get("StateValue"),
                                "reason": (a.get("StateReason") or "")[:200]})
            token = resp.get("NextToken")
            if not token:
                break
        return out
    except Exception:
        return []


def recent_log_errors(session, region: str, service: str, name: str, minutes: int = 180) -> list:
    """Recent error lines from the resource's conventional log group (Lambda only for now)."""
    group = {"lambda": f"/aws/lambda/{name}"}.get((service or "").lower())
    if not group:
        return []
    try:
        logs = client(session, "logs", region)
        start = int((datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp() * 1000)
        resp = logs.filter_log_events(logGroupName=group, startTime=start,
                                      filterPattern=_LOG_FILTER, limit=25)
        return [e.get("message", "").strip() for e in resp.get("events", [])][:25]
    except Exception:
        return []


def recent_changes(session, region: str, resource_name: str, days: int = 7) -> list:
    """Recent mutating CloudTrail events referencing the resource."""
    try:
        ct = client(session, "cloudtrail", region)
        start = datetime.now(timezone.utc) - timedelta(days=days)
        resp = ct.lookup_events(
            LookupAttributes=[{"AttributeKey": "ResourceName", "AttributeValue": resource_name}],
            StartTime=start, MaxResults=15)
        out = []
        for e in resp.get("Events", []):
            name = e.get("EventName", "")
            if name.startswith(("Get", "List", "Describe", "Lookup", "BatchGet")):
                continue  # skip reads
            out.append({"event": name, "user": e.get("Username", ""),
                        "time": str(e.get("EventTime", ""))})
        return out[:10]
    except Exception:
        return []
