import boto3
import pytest
from botocore.stub import Stubber

from apps.dashboard.data import DrillLevel, breadcrumb_to_query, CostDashboardData
from finops_core.cost.explorer import CostExplorer


def test_breadcrumb_root_is_service():
    assert breadcrumb_to_query([]) == ("SERVICE", {})


def test_breadcrumb_descends_in_order():
    stack = [DrillLevel("SERVICE", "Amazon EC2")]
    nxt, filters = breadcrumb_to_query(stack)
    assert nxt == "USAGE_TYPE"
    assert filters == {"SERVICE": "Amazon EC2"}

    stack.append(DrillLevel("USAGE_TYPE", "BoxUsage:m5.large"))
    nxt, filters = breadcrumb_to_query(stack)
    assert nxt == "OPERATION"
    assert filters == {"SERVICE": "Amazon EC2", "USAGE_TYPE": "BoxUsage:m5.large"}


def test_breadcrumb_fully_drilled_returns_none():
    stack = [DrillLevel(d, "x") for d in ("SERVICE", "USAGE_TYPE", "OPERATION", "REGION", "LINKED_ACCOUNT")]
    nxt, _ = breadcrumb_to_query(stack)
    assert nxt is None


RESPONSE = {
    "ResultsByTime": [{
        "TimePeriod": {"Start": "2026-06-01", "End": "2026-06-19"}, "Estimated": True, "Total": {},
        "Groups": [
            {"Keys": ["Amazon EC2"], "Metrics": {"UnblendedCost": {"Amount": "40.0", "Unit": "USD"}}},
            {"Keys": ["Amazon S3"], "Metrics": {"UnblendedCost": {"Amount": "10.0", "Unit": "USD"}}},
        ],
    }]
}


def test_breakdown_root_groups_by_service():
    client = boto3.client("ce", region_name="us-east-1",
                          aws_access_key_id="x", aws_secret_access_key="y", aws_session_token="z")
    with Stubber(client) as stub:
        stub.add_response("get_cost_and_usage", RESPONSE)
        data = CostDashboardData(ce=CostExplorer(ce_client=client))
        b = data.breakdown([], period="mtd", top_n=10)
    assert b.group_by == "SERVICE"
    assert b.total == 50.0
    assert b.groups[0].key == "Amazon EC2"
