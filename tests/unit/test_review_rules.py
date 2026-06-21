"""Best-practice RULES per service — pure functions over a config/metrics snapshot (no AWS).
These produce the deterministic, AWS-doc-cited findings the agent narrates."""
from devops_core.review.rules.ec2 import ec2_findings
from devops_core.review.rules.lambda_ import lambda_findings
from devops_core.review.rules.rds import rds_findings
from devops_core.review.rules.s3 import s3_findings
from devops_core.review.schemas import ServiceReview


def _ids(findings):
    return {f.rule_id for f in findings}


def test_every_finding_has_doc_and_valid_severity():
    fs = lambda_findings(
        {"Runtime": "python3.8", "MemorySize": 128, "Timeout": 900,
         "Architectures": ["x86_64"], "TracingConfig": {"Mode": "PassThrough"},
         "Environment": {"Variables": {"DB_PASSWORD": "hunter2"}}},
        {"Errors": {"sum": 5}, "Throttles": {"sum": 3}, "Duration": {"max": 880000}})
    assert fs, "expected findings for a poorly-configured lambda"
    for f in fs:
        assert f.doc_url.startswith("https://"), f"{f.rule_id} missing doc"
        assert f.severity in ("critical", "high", "medium", "low", "info")
        assert f.current and f.recommended


def test_lambda_flags_the_big_ones():
    ids = _ids(lambda_findings(
        {"Runtime": "python3.8", "MemorySize": 128, "Timeout": 900,
         "Architectures": ["x86_64"], "TracingConfig": {"Mode": "PassThrough"},
         "Environment": {"Variables": {"API_SECRET": "x"}}},
        {"Errors": {"sum": 5}, "Throttles": {"sum": 3}, "Duration": {"max": 870000}}))
    assert {"lambda.runtime.deprecated", "lambda.arch.graviton",
            "lambda.tracing.disabled", "lambda.env.plaintext_secret",
            "lambda.errors.present", "lambda.throttles.present"} <= ids


def test_lambda_healthy_has_no_high_findings():
    fs = lambda_findings(
        {"Runtime": "python3.12", "MemorySize": 512, "Timeout": 30,
         "Architectures": ["arm64"], "TracingConfig": {"Mode": "Active"},
         "Environment": {"Variables": {"LOG_LEVEL": "INFO"}}},
        {"Errors": {"sum": 0}, "Throttles": {"sum": 0}, "Duration": {"max": 1200}})
    assert not [f for f in fs if f.severity in ("critical", "high")]


def test_ec2_previous_gen_and_idle():
    ids = _ids(ec2_findings(
        {"InstanceType": "t2.micro", "Monitoring": {"State": "disabled"},
         "EbsOptimized": False, "PublicIpAddress": "1.2.3.4"},
        {"CPUUtilization": {"avg": 2.5, "max": 8.0}}))
    assert "ec2.gen.previous" in ids
    assert "ec2.cpu.underutilized" in ids


def test_rds_security_and_reliability():
    ids = _ids(rds_findings(
        {"DBInstanceClass": "db.t2.small", "Engine": "mysql", "MultiAZ": False,
         "StorageEncrypted": False, "PubliclyAccessible": True,
         "BackupRetentionPeriod": 0, "StorageType": "gp2"}, {}))
    assert {"rds.public", "rds.encryption.disabled", "rds.multiaz.disabled",
            "rds.backups.disabled", "rds.storage.gp3"} <= ids
    # public + unencrypted are the worst
    crit = {f.rule_id for f in rds_findings(
        {"PubliclyAccessible": True, "StorageEncrypted": False}, {})
        if f.severity == "critical"}
    assert "rds.public" in crit


def test_s3_security_baseline():
    ids = _ids(s3_findings({
        "encryption": None, "public_access_block": {"BlockPublicAcls": False},
        "versioning": "Disabled", "lifecycle": None}))
    assert {"s3.encryption.missing", "s3.public_access.open",
            "s3.versioning.disabled"} <= ids


def test_review_sorts_and_limits():
    r = ServiceReview(service="lambda", resource_id="f", findings=lambda_findings(
        {"Runtime": "python3.8", "MemorySize": 128, "Architectures": ["x86_64"],
         "TracingConfig": {"Mode": "PassThrough"}}, {}))
    d = r.to_dict(limit=2)
    assert len(d["findings"]) == 2
    sev = [f["severity"] for f in d["findings"]]
    assert sev == sorted(sev, key=["critical", "high", "medium", "low", "info"].index)
    assert d["finding_count"] >= 2 and d["by_severity"]
