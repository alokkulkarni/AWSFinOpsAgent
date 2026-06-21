"""Amazon EC2 best-practice rules — instance config + CloudWatch CPU."""
from __future__ import annotations

from devops_core.review.schemas import Finding

_DOC = "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/"
# Previous-generation families (current gen are *5/*6/*7 and Graviton g-suffixed).
_PREV_GEN = ("t1.", "t2.", "m1.", "m2.", "m3.", "m4.", "c1.", "c3.", "c4.",
             "r3.", "r4.", "i2.", "i3.", "d2.", "p2.", "g2.", "g3.")


def ec2_findings(config: dict, metrics: dict | None = None) -> list:
    metrics = metrics or {}
    out: list[Finding] = []
    itype = config.get("InstanceType") or ""
    monitoring = (config.get("Monitoring") or {}).get("State")

    if itype.startswith(_PREV_GEN):
        out.append(Finding(
            "ec2.gen.previous", "Previous-generation instance type", "medium",
            current=itype, recommended="current gen (e.g. m7i/c7g/Graviton)",
            rationale="Newer families give better price-performance; many are a drop-in upgrade.",
            category="cost", doc_url=_DOC + "instance-types.html"))

    if monitoring == "disabled":
        out.append(Finding(
            "ec2.monitoring.disabled", "Detailed monitoring disabled", "low",
            current="basic (5-min)", recommended="detailed (1-min) for prod",
            rationale="1-minute metrics improve autoscaling responsiveness and incident detection.",
            category="reliability", doc_url=_DOC + "using-cloudwatch-new.html"))

    if config.get("EbsOptimized") is False:
        out.append(Finding(
            "ec2.ebs.not_optimized", "EBS optimization off", "low",
            current="not EBS-optimized", recommended="enable EBS optimization",
            rationale="Dedicated EBS throughput avoids contention with network traffic on most "
                      "current instance types (where it isn't already on by default).",
            category="performance", doc_url=_DOC + "ebs-optimized.html"))

    if config.get("PublicIpAddress"):
        out.append(Finding(
            "ec2.public_ip", "Instance has a public IP", "info",
            current=config["PublicIpAddress"], recommended="prefer private subnets + NAT/ALB",
            rationale="Public IPs increase attack surface; confirm it's intended and SGs are tight.",
            category="security", doc_url=_DOC + "ec2-instance-addressing.html"))

    cpu = metrics.get("CPUUtilization") or {}
    avg = cpu.get("avg")
    if avg is not None and avg < 5:
        out.append(Finding(
            "ec2.cpu.underutilized", "CPU consistently very low", "medium",
            current=f"avg {avg:.1f}%", recommended="downsize / consolidate / Compute Optimizer",
            rationale="Sustained low utilization signals over-provisioning; rightsize for cost.",
            category="cost", doc_url=_DOC + "monitoring_ec2.html"))
    elif avg is not None and avg > 85:
        out.append(Finding(
            "ec2.cpu.saturated", "CPU consistently high", "medium",
            current=f"avg {avg:.1f}%", recommended="scale up/out",
            rationale="Sustained high CPU risks latency/availability under peak load.",
            category="performance", doc_url=_DOC + "monitoring_ec2.html"))

    return out
