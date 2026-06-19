"""Digest delivery adapters: file (default), Slack webhook, SNS, SES. Outbound channels are
opt-in and configured by env; `file` is always safe."""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from finops_core.config import Config

_EXT = {"md": "md", "html": "html", "json": "json"}


def _to_file(report: str, fmt: str, out: str | None = None) -> str:
    if out:
        path = Path(out)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        path = Path("reports") / f"digest-{stamp}.{_EXT.get(fmt, 'txt')}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report)
    return str(path)


def _to_slack(report: str) -> str:
    url = os.getenv("FINOPS_SLACK_WEBHOOK")
    if not url:
        return "skipped (FINOPS_SLACK_WEBHOOK not set)"
    data = json.dumps({"text": report[:39000]}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
        return f"slack {r.status}"


def _to_sns(report: str, cfg: Config, session=None) -> str:
    arn = os.getenv("FINOPS_SNS_TOPIC_ARN")
    if not arn:
        return "skipped (FINOPS_SNS_TOPIC_ARN not set)"
    from finops_core.aws.session import build_session, client
    sns = client(session or build_session(cfg), "sns", region=cfg.aws.region)
    sns.publish(TopicArn=arn, Subject="AWS FinOps Digest", Message=report[:250000])
    return "sns published"


def _to_ses(report: str, cfg: Config, session=None) -> str:
    to, frm = os.getenv("FINOPS_SES_TO"), os.getenv("FINOPS_SES_FROM")
    if not (to and frm):
        return "skipped (FINOPS_SES_TO/FROM not set)"
    from finops_core.aws.session import build_session, client
    ses = client(session or build_session(cfg), "ses", region=cfg.aws.region)
    ses.send_email(Source=frm, Destination={"ToAddresses": [to]},
                   Message={"Subject": {"Data": "AWS FinOps Digest"},
                            "Body": {"Text": {"Data": report}}})
    return "ses sent"


def deliver(report: str, fmt: str, targets: list, cfg: Config, session=None, out: str | None = None) -> dict:
    results = {}
    for t in targets:
        try:
            if t == "file":
                results["file"] = _to_file(report, fmt, out)
            elif t == "slack":
                results["slack"] = _to_slack(report)
            elif t == "sns":
                results["sns"] = _to_sns(report, cfg, session)
            elif t == "ses":
                results["ses"] = _to_ses(report, cfg, session)
            else:
                results[t] = "unknown target"
        except Exception as e:
            results[t] = f"error: {e}"
    return results
