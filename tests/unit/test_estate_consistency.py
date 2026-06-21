"""Inventory accuracy guard: the Estate aggregations must reconcile with the resource list."""
from devops_core.schemas.estate import Estate, Resource

RS = [Resource.from_arn(a) for a in [
    "arn:aws:ec2:eu-west-2:1:instance/i-1",
    "arn:aws:ec2:us-east-1:1:instance/i-2",
    "arn:aws:s3:::b",
    "arn:aws:lambda:eu-west-2:2:function:f",
]]


def test_service_counts_sum_to_total():
    est = Estate(resources=RS)
    assert sum(est.counts("service").values()) == len(RS)


def test_region_counts_sum_to_total():
    est = Estate(resources=RS)
    # s3 ARN has no region -> bucketed as "?"; still counted exactly once
    assert sum(est.counts("region").values()) == len(RS)


def test_accounts_property_dedupes():
    est = Estate(resources=RS)
    assert est.accounts == ["1", "2"]
    assert sum(est.counts("account").values()) == len(RS)
