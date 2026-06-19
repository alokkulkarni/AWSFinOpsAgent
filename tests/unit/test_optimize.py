import boto3
import pytest
from botocore.stub import Stubber

from finops_core.optimize import engine as eng
from finops_core.optimize.engine import Optimizer, _money
from finops_core.schemas.optimize import Recommendation


def test_money_handles_shapes():
    assert _money({"Amount": "1.50"}) == 1.5
    assert _money({"value": 2.0}) == 2.0
    assert _money("3.25") == 3.25
    assert _money(None) == 0.0
    assert _money({"nope": 1}) == 0.0


def _ce_with(method, response):
    c = boto3.client("ce", region_name="us-east-1",
                     aws_access_key_id="x", aws_secret_access_key="y", aws_session_token="z")
    stub = Stubber(c)
    stub.add_response(method, response)
    stub.activate()
    return c


def test_rightsizing_normalizes(monkeypatch):
    resp = {"RightsizingRecommendations": [
        {"AccountId": "123", "RightsizingType": "MODIFY",
         "CurrentInstance": {"ResourceId": "i-abc",
                             "ResourceDetails": {"EC2ResourceDetails": {"InstanceType": "m5.xlarge"}}},
         "ModifyRecommendationDetail": {"TargetInstances": [
             {"EstimatedMonthlySavings": "30.00",
              "ResourceDetails": {"EC2ResourceDetails": {"InstanceType": "m5.large"}}}]}},
        {"AccountId": "123", "RightsizingType": "TERMINATE",
         "CurrentInstance": {"ResourceId": "i-idle",
                             "ResourceDetails": {"EC2ResourceDetails": {"InstanceType": "t3.large"}}},
         "TerminateRecommendationDetail": {"EstimatedMonthlySavings": "50.00"}},
    ]}
    c = _ce_with("get_rightsizing_recommendation", resp)
    monkeypatch.setattr(eng, "client", lambda session, service, region=None: c)

    recs, notes = Optimizer().rightsizing()
    assert notes == []
    by_action = {r.action: r for r in recs}
    assert by_action["terminate"].monthly_savings == 50.0
    assert by_action["terminate"].category == "idle"
    assert by_action["modify"].monthly_savings == 30.0
    assert by_action["modify"].recommended == "m5.large"


def test_savings_plans_normalizes(monkeypatch):
    resp = {"SavingsPlansPurchaseRecommendation": {"SavingsPlansPurchaseRecommendationSummary": {
        "EstimatedMonthlySavingsAmount": "42.00", "HourlyCommitmentToPurchase": "0.5",
        "EstimatedSavingsPercentage": "15"}}}
    c = _ce_with("get_savings_plans_purchase_recommendation", resp)
    monkeypatch.setattr(eng, "client", lambda session, service, region=None: c)

    recs, notes = Optimizer().savings_plans()
    assert len(recs) == 1 and recs[0].monthly_savings == 42.0
    assert recs[0].category == "commitment"


def test_all_recommendations_dedupes_and_ranks(monkeypatch):
    opt = Optimizer()
    r_low = Recommendation(source="a", title="x", category="rightsize",
                           monthly_savings=10, resource_id="i-1", action="modify")
    r_high = Recommendation(source="b", title="x", category="rightsize",
                            monthly_savings=25, resource_id="i-1", action="modify")  # same key
    r_other = Recommendation(source="c", title="y", category="commitment",
                             monthly_savings=5, action="purchase")
    monkeypatch.setattr(opt, "rightsizing", lambda: ([r_low, r_high], []))
    monkeypatch.setattr(opt, "compute_optimizer", lambda: ([], ["co not enrolled"]))
    monkeypatch.setattr(opt, "savings_plans", lambda: ([r_other], []))
    monkeypatch.setattr(opt, "reservations", lambda: ([], []))
    monkeypatch.setattr(opt, "cost_optimization_hub", lambda: ([], []))
    monkeypatch.setattr(opt, "trusted_advisor_cost", lambda: ([], []))

    report = opt.all_recommendations()
    assert report.count == 2                              # r_low/r_high collapsed
    assert report.recommendations[0].monthly_savings == 25   # ranked desc, kept higher
    assert report.total_monthly_savings == 30.0          # 25 + 5
    assert "co not enrolled" in report.notes
