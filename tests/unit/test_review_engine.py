"""Dispatch helpers: service inference + resource-name extraction + generic fallback (no AWS)."""
from devops_core.review.engine import infer_service, resource_name, review_service


def test_infer_from_explicit_and_aliases():
    assert infer_service("lambda", "f") == "lambda"
    assert infer_service("Function", "f") == "lambda"
    assert infer_service("database", "mydb") == "rds"


def test_infer_from_arn_and_id():
    assert infer_service("", "arn:aws:rds:eu-west-2:1:db:prod") == "rds"
    assert infer_service("", "arn:aws:s3:::my-bucket") == "s3"
    assert infer_service("", "i-0abc123") == "ec2"


def test_resource_name_extraction():
    assert resource_name("ec2", "arn:aws:ec2:eu-west-2:1:instance/i-0abc") == "i-0abc"
    assert resource_name("rds", "arn:aws:rds:eu-west-2:1:db:prod") == "prod"
    assert resource_name("s3", "arn:aws:s3:::my-bucket") == "my-bucket"
    assert resource_name("lambda", "arn:aws:lambda:eu-west-2:1:function:f") == \
        "arn:aws:lambda:eu-west-2:1:function:f"  # API accepts the ARN


def test_generic_fallback_does_not_touch_aws():
    # session/cfg passed so no build_session; unknown service -> note, no AWS call
    r = review_service("kinesis", "my-stream", region="eu-west-2",
                       session=object(), cfg=object())
    d = r.to_dict()
    assert d["finding_count"] == 0
    assert d["notes"] and "Well-Architected" in d["notes"][0]
