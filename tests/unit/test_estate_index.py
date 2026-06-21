from devops_core.discovery.index import EstateIndex
from devops_core.schemas.estate import Estate, Resource

EST = Estate(
    resources=[
        Resource.from_arn("arn:aws:ec2:eu-west-2:1:instance/i-web", tags={"Name": "web", "app": "frontend"}),
        Resource.from_arn("arn:aws:ec2:eu-west-2:1:instance/i-db"),
        Resource.from_arn("arn:aws:lambda:us-east-1:1:function:proc"),
        Resource.from_arn("arn:aws:s3:::data-bucket"),
    ],
    source="test",
)


def _idx():
    return EstateIndex(estate=EST)


def test_summary_has_counts_not_resource_list():
    s = _idx().summary()
    assert s["count"] == 4
    assert s["by_service"]["ec2"] == 2
    assert "resources" not in s


def test_list_filters_by_service():
    r = _idx().list(service="ec2")
    assert r["count"] == 2
    assert all(x["service"] == "ec2" for x in r["resources"])


def test_describe_by_id():
    d = _idx().describe("i-web")
    assert d["id"] == "i-web" and d["tags"]["Name"] == "web"


def test_find_by_tag_value():
    r = _idx().find("frontend")
    assert r["count"] >= 1


def test_find_by_service():
    r = _idx().find("lambda")
    assert any(x["service"] == "lambda" for x in r["resources"])
