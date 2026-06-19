import boto3
import pytest
from botocore.stub import Stubber

from finops_core.cost.explorer import CostExplorer


@pytest.fixture
def stubbed_ce():
    client = boto3.client(
        "ce", region_name="us-east-1",
        aws_access_key_id="x", aws_secret_access_key="y", aws_session_token="z",
    )
    stub = Stubber(client)
    with stub:
        yield client, stub


# ---- pure helpers (no AWS) ------------------------------------------------- #
def test_group_key_dimension_tag_costcategory():
    assert CostExplorer._group_key("SERVICE") == {"Type": "DIMENSION", "Key": "SERVICE"}
    assert CostExplorer._group_key("TAG:Environment") == {"Type": "TAG", "Key": "Environment"}
    assert CostExplorer._group_key("COST_CATEGORY:Team") == {"Type": "COST_CATEGORY", "Key": "Team"}


def test_build_filter_single_and_multi():
    assert CostExplorer._build_filter({"SERVICE": "Amazon EC2"}) == {
        "Dimensions": {"Key": "SERVICE", "Values": ["Amazon EC2"]}
    }
    multi = CostExplorer._build_filter({"SERVICE": "Amazon EC2", "TAG:Env": ["prod", "dev"]})
    assert "And" in multi and len(multi["And"]) == 2


GROUPED_RESPONSE = {
    "ResultsByTime": [
        {
            "TimePeriod": {"Start": "2026-01-01", "End": "2026-02-01"}, "Estimated": False,
            "Total": {},
            "Groups": [
                {"Keys": ["Amazon Elastic Compute Cloud - Compute"],
                 "Metrics": {"UnblendedCost": {"Amount": "100.0", "Unit": "USD"}}},
                {"Keys": ["Amazon Simple Storage Service"],
                 "Metrics": {"UnblendedCost": {"Amount": "20.0", "Unit": "USD"}}},
                {"Keys": ["AWS Lambda"],
                 "Metrics": {"UnblendedCost": {"Amount": "5.0", "Unit": "USD"}}},
            ],
        },
        {
            "TimePeriod": {"Start": "2026-02-01", "End": "2026-03-01"}, "Estimated": True,
            "Total": {},
            "Groups": [
                {"Keys": ["Amazon Elastic Compute Cloud - Compute"],
                 "Metrics": {"UnblendedCost": {"Amount": "50.0", "Unit": "USD"}}},
                {"Keys": ["Amazon Simple Storage Service"],
                 "Metrics": {"UnblendedCost": {"Amount": "10.0", "Unit": "USD"}}},
                {"Keys": ["Amazon CloudWatch"],
                 "Metrics": {"UnblendedCost": {"Amount": "3.0", "Unit": "USD"}}},
            ],
        },
    ]
}


def test_cost_by_service_aggregates_sorts_and_truncates(stubbed_ce):
    client, stub = stubbed_ce
    stub.add_response("get_cost_and_usage", GROUPED_RESPONSE)
    ce = CostExplorer(ce_client=client)

    b = ce.cost_by_service(start="2026-01-01", end="2026-03-01", top_n=2)

    assert b.total == 188.0                      # 150 + 30 + 5 + 3
    assert b.estimated is True                   # second month estimated
    assert b.groups[0].key.startswith("Amazon Elastic Compute Cloud")
    assert b.groups[0].amount == 150.0           # summed across both months
    assert [g.key for g in b.groups] == [
        "Amazon Elastic Compute Cloud - Compute", "Amazon Simple Storage Service"]
    assert b.others == 8.0                        # Lambda(5) + CloudWatch(3)
    assert round(b.groups[0].pct, 1) == 79.8      # 150/188


def test_total_equals_groups_plus_others(stubbed_ce):
    client, stub = stubbed_ce
    stub.add_response("get_cost_and_usage", GROUPED_RESPONSE)
    ce = CostExplorer(ce_client=client)

    b = ce.cost_by_service(start="2026-01-01", end="2026-03-01", top_n=2)
    assert round(sum(g.amount for g in b.groups) + (b.others or 0.0), 6) == b.total
