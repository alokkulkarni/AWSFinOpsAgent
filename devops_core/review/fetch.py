"""Per-service fetchers — pull live config + CloudWatch metrics, then run the rules.
Each returns a ServiceReview. Graceful: a failed describe yields a noted, empty review."""
from __future__ import annotations

from finops_core.aws.session import client
from devops_core.review.metrics import metric_stats
from devops_core.review.rules.ec2 import ec2_findings
from devops_core.review.rules.lambda_ import lambda_findings
from devops_core.review.rules.rds import rds_findings
from devops_core.review.rules.s3 import s3_findings
from devops_core.review.schemas import ServiceReview


def review_lambda(session, region, name, include_code=True) -> ServiceReview:
    lam = client(session, "lambda", region)
    try:
        cfg = lam.get_function_configuration(FunctionName=name)
    except Exception as e:
        return ServiceReview("lambda", name, region,
                             notes=[f"get_function_configuration: {type(e).__name__}"])
    metrics = {
        "Errors": metric_stats(session, region, "AWS/Lambda", "Errors",
                               {"FunctionName": name}, stats=("Sum",)),
        "Throttles": metric_stats(session, region, "AWS/Lambda", "Throttles",
                                  {"FunctionName": name}, stats=("Sum",)),
        "Duration": metric_stats(session, region, "AWS/Lambda", "Duration",
                                 {"FunctionName": name}, stats=("Average", "Maximum")),
    }
    summary = {k: cfg.get(k) for k in
               ("Runtime", "MemorySize", "Timeout", "Architectures", "PackageType", "Handler")}
    summary["TracingMode"] = (cfg.get("TracingConfig") or {}).get("Mode")
    review = ServiceReview("lambda", name, region, summary=summary, metrics=metrics,
                           findings=lambda_findings(cfg, metrics))
    if include_code and cfg.get("PackageType", "Zip") == "Zip":
        from devops_core.review.lambda_code import analyze_lambda_code
        cf, notes = analyze_lambda_code(lam, name, cfg.get("Runtime", ""))
        review.findings.extend(cf)
        review.notes.extend(notes)
    return review


def review_ec2(session, region, instance_id, **_) -> ServiceReview:
    ec2 = client(session, "ec2", region)
    try:
        res = ec2.describe_instances(InstanceIds=[instance_id])
        inst = res["Reservations"][0]["Instances"][0]
    except Exception as e:
        return ServiceReview("ec2", instance_id, region,
                             notes=[f"describe_instances: {type(e).__name__}"])
    metrics = {"CPUUtilization": metric_stats(
        session, region, "AWS/EC2", "CPUUtilization", {"InstanceId": instance_id})}
    summary = {k: inst.get(k) for k in
               ("InstanceType", "Architecture", "EbsOptimized", "PublicIpAddress")}
    summary["State"] = (inst.get("State") or {}).get("Name")
    return ServiceReview("ec2", instance_id, region, summary=summary, metrics=metrics,
                         findings=ec2_findings(inst, metrics))


def review_rds(session, region, db_id, **_) -> ServiceReview:
    rds = client(session, "rds", region)
    try:
        db = rds.describe_db_instances(DBInstanceIdentifier=db_id)["DBInstances"][0]
    except Exception as e:
        return ServiceReview("rds", db_id, region,
                             notes=[f"describe_db_instances: {type(e).__name__}"])
    metrics = {"CPUUtilization": metric_stats(
        session, region, "AWS/RDS", "CPUUtilization", {"DBInstanceIdentifier": db_id})}
    summary = {k: db.get(k) for k in
               ("Engine", "EngineVersion", "DBInstanceClass", "MultiAZ", "StorageType",
                "AllocatedStorage", "StorageEncrypted", "PubliclyAccessible",
                "BackupRetentionPeriod")}
    return ServiceReview("rds", db_id, region, summary=summary, metrics=metrics,
                         findings=rds_findings(db, metrics))


def review_s3(session, region, bucket, **_) -> ServiceReview:
    s3 = client(session, "s3", region or "us-east-1")
    notes: list = []

    def _try(fn, label):
        try:
            return fn()
        except Exception as e:
            notes.append(f"{label}: {type(e).__name__}")
            return None

    snap = {
        "encryption": _try(
            lambda: s3.get_bucket_encryption(Bucket=bucket).get("ServerSideEncryptionConfiguration"),
            "encryption"),
        "public_access_block": _try(
            lambda: s3.get_public_access_block(Bucket=bucket).get(
                "PublicAccessBlockConfiguration"), "public_access_block"),
        "versioning": _try(
            lambda: s3.get_bucket_versioning(Bucket=bucket).get("Status"), "versioning"),
        "lifecycle": _try(
            lambda: s3.get_bucket_lifecycle_configuration(Bucket=bucket).get("Rules"), "lifecycle"),
        "logging": _try(
            lambda: s3.get_bucket_logging(Bucket=bucket).get("LoggingEnabled"), "logging"),
    }
    return ServiceReview("s3", bucket, region, summary=snap,
                         findings=s3_findings(snap), notes=notes)
