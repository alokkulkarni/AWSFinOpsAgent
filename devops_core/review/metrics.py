"""CloudWatch metric snapshot helper for reviews — graceful (failures → {})."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from finops_core.aws.session import client


def metric_stats(session, region: str, namespace: str, metric: str, dimensions: dict,
                 stats=("Average", "Maximum"), hours: int = 72, period: int = 3600) -> dict:
    """Aggregate a CloudWatch metric over a recent window → {datapoints, avg?, max?, sum?}."""
    try:
        cw = client(session, "cloudwatch", region)
        end = datetime.now(timezone.utc)
        resp = cw.get_metric_statistics(
            Namespace=namespace, MetricName=metric,
            Dimensions=[{"Name": k, "Value": v} for k, v in dimensions.items()],
            StartTime=end - timedelta(hours=hours), EndTime=end,
            Period=period, Statistics=list(stats))
        dps = resp.get("Datapoints", [])
        if not dps:
            return {}
        out: dict = {"datapoints": len(dps)}
        if "Average" in stats:
            vals = [d["Average"] for d in dps if "Average" in d]
            if vals:
                out["avg"] = sum(vals) / len(vals)
        if "Maximum" in stats:
            vals = [d["Maximum"] for d in dps if "Maximum" in d]
            if vals:
                out["max"] = max(vals)
        if "Sum" in stats:
            out["sum"] = sum(d.get("Sum", 0) for d in dps)
        return out
    except Exception:
        return {}
