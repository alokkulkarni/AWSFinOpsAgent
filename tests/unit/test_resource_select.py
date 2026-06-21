"""Resource-picker choices for the DevOps review/diagnose panel (pure helper)."""
from apps.dashboard.resource_select import resource_choices

RES = [
    {"service": "lambda", "id": "fn-a", "arn": "arn:aws:lambda:eu-west-2:1:function:fn-a",
     "region": "eu-west-2", "name": "Alpha"},
    {"service": "lambda", "id": "fn-b", "arn": "", "region": "eu-west-2", "name": None},
    {"service": "ec2", "id": "i-1", "arn": "arn:aws:ec2:eu-west-2:1:instance/i-1",
     "region": "eu-west-2", "name": "web"},
    {"service": "lambda", "id": "fn-a", "arn": "arn:aws:lambda:eu-west-2:1:function:fn-a",
     "region": "eu-west-2", "name": "Alpha"},  # duplicate
]


def test_filters_by_service_and_prefers_arn():
    ids = {c["id"] for c in resource_choices(RES, "lambda")}
    assert "arn:aws:lambda:eu-west-2:1:function:fn-a" in ids  # ARN preferred
    assert "fn-b" in ids                                       # falls back to id when no ARN
    assert all(c["service"] == "lambda" for c in resource_choices(RES, "lambda"))


def test_dedupes_and_sorts_by_label():
    ch = resource_choices(RES, "lambda")
    ids = [c["id"] for c in ch]
    assert len(ids) == len(set(ids))                          # fn-a appears once
    assert [c["label"] for c in ch] == sorted([c["label"] for c in ch], key=str.lower)


def test_empty_for_absent_service():
    assert resource_choices(RES, "rds") == []
