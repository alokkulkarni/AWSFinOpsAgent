"""Accuracy invariant: the cost-per-service breakdown must total the same as the period
summary over identical underlying data. (Real-AWS equivalence is checked in the verify step.)"""
import boto3
import pytest
from botocore.stub import Stubber

from finops_core.cost.explorer import CostExplorer

# Same underlying spend, expressed grouped vs. as period totals.
GROUPED = {
    "ResultsByTime": [{
        "TimePeriod": {"Start": "2026-05-01", "End": "2026-06-01"}, "Estimated": False, "Total": {},
        "Groups": [
            {"Keys": ["Amazon EC2"], "Metrics": {"UnblendedCost": {"Amount": "120.50", "Unit": "USD"}}},
            {"Keys": ["Amazon S3"], "Metrics": {"UnblendedCost": {"Amount": "33.25", "Unit": "USD"}}},
            {"Keys": ["AWS Lambda"], "Metrics": {"UnblendedCost": {"Amount": "6.25", "Unit": "USD"}}},
        ],
    }]
}
SUMMARY = {
    "ResultsByTime": [{
        "TimePeriod": {"Start": "2026-05-01", "End": "2026-06-01"}, "Estimated": False,
        "Total": {"UnblendedCost": {"Amount": "160.00", "Unit": "USD"}}, "Groups": [],
    }]
}


@pytest.fixture
def ce_client():
    client = boto3.client(
        "ce", region_name="us-east-1",
        aws_access_key_id="x", aws_secret_access_key="y", aws_session_token="z",
    )
    with Stubber(client) as stub:
        yield client, stub


def test_by_service_total_matches_summary_total(ce_client):
    client, stub = ce_client
    stub.add_response("get_cost_and_usage", GROUPED)
    stub.add_response("get_cost_and_usage", SUMMARY)
    ce = CostExplorer(ce_client=client)

    by_service = ce.cost_by_service(start="2026-05-01", end="2026-06-01")
    summary = ce.summary(start="2026-05-01", end="2026-06-01")

    assert by_service.total == summary.total == 160.0
