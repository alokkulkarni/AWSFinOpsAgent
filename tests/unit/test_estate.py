from devops_core.schemas.estate import Estate, Resource, parse_arn


def test_parse_arn_ec2_instance():
    p = parse_arn("arn:aws:ec2:eu-west-2:395402194296:instance/i-0abc")
    assert p["service"] == "ec2"
    assert p["region"] == "eu-west-2"
    assert p["account"] == "395402194296"
    assert p["id"] == "i-0abc"
    assert p["resource_type"] == "ec2:instance"


def test_parse_arn_s3_bucket():
    p = parse_arn("arn:aws:s3:::my-bucket")
    assert p["service"] == "s3"
    assert p["id"] == "my-bucket"
    assert p["region"] is None and p["account"] is None


def test_resource_from_arn_lambda_colon_form():
    r = Resource.from_arn("arn:aws:lambda:us-east-1:123:function:myfn", tags={"env": "prod"})
    assert r.service == "lambda" and r.region == "us-east-1" and r.account == "123"
    assert r.id == "myfn" and r.tags["env"] == "prod"


def test_estate_aggregation_and_dedup():
    rs = [
        Resource.from_arn("arn:aws:ec2:eu-west-2:1:instance/i-1"),
        Resource.from_arn("arn:aws:ec2:eu-west-2:1:instance/i-1"),   # duplicate
        Resource.from_arn("arn:aws:s3:::b1"),
    ]
    seen = {r.key(): r for r in rs}
    est = Estate(resources=list(seen.values()))
    assert len(est.resources) == 2
    assert est.counts("service")["ec2"] == 1
    assert est.counts("service")["s3"] == 1
    assert est.regions == ["eu-west-2"]
    assert est.accounts == ["1"]
