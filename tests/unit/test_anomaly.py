import boto3
from botocore.stub import Stubber

from finops_core.anomaly.engine import AnomalyEngine


def _client(service, region="us-east-1"):
    return boto3.client(service, region_name=region,
                        aws_access_key_id="x", aws_secret_access_key="y", aws_session_token="z")


def test_anomalies_rank_and_root_causes(monkeypatch):
    ce = _client("ce")
    stub = Stubber(ce)
    stub.add_response("get_anomaly_monitors", {"AnomalyMonitors": [
        {"MonitorArn": "arn:m1", "MonitorName": "m1", "MonitorType": "DIMENSIONAL",
         "MonitorDimension": "SERVICE"}]})
    stub.add_response("get_anomalies", {"Anomalies": [
        {"AnomalyId": "a1", "AnomalyStartDate": "2026-06-10", "MonitorArn": "arn:m1",
         "Impact": {"TotalImpact": 5.0, "MaxImpact": 3.0},
         "AnomalyScore": {"MaxScore": 0.9, "CurrentScore": 0.9},
         "DimensionValue": "AmazonEC2", "RootCauses": [{"Service": "AmazonEC2", "Region": "us-east-1"}]},
        {"AnomalyId": "a2", "AnomalyStartDate": "2026-06-11", "MonitorArn": "arn:m1",
         "Impact": {"TotalImpact": 10.0, "MaxImpact": 8.0},
         "AnomalyScore": {"MaxScore": 0.5, "CurrentScore": 0.5},
         "DimensionValue": "AmazonS3", "RootCauses": []},
    ]})
    stub.activate()

    eng = AnomalyEngine()
    monkeypatch.setattr(eng, "_client", lambda service, region=None: ce)
    rep = eng.anomalies(start="2026-06-01", end="2026-06-30")

    assert rep.count == 2
    assert rep.anomalies[0].dimension == "AmazonS3"      # ranked by impact (10 > 5)
    assert rep.total_impact == 15.0
    assert "us-east-1" in rep.anomalies[1].root_causes[0]


def test_budgets_breach_flags(monkeypatch):
    sts = _client("sts")
    sts_stub = Stubber(sts)
    sts_stub.add_response("get_caller_identity",
                          {"UserId": "u", "Account": "123456789012", "Arn": "arn:aws:iam::123456789012:root"})
    sts_stub.activate()

    bud = _client("budgets")
    bud_stub = Stubber(bud)
    bud_stub.add_response("describe_budgets", {"Budgets": [{
        "BudgetName": "B", "BudgetLimit": {"Amount": "100", "Unit": "USD"},
        "TimeUnit": "MONTHLY", "BudgetType": "COST",
        "CalculatedSpend": {"ActualSpend": {"Amount": "150", "Unit": "USD"},
                            "ForecastedSpend": {"Amount": "200", "Unit": "USD"}}}]})
    bud_stub.activate()

    eng = AnomalyEngine()
    monkeypatch.setattr(eng, "_client", lambda service, region=None: {"sts": sts, "budgets": bud}[service])
    rep = eng.budgets()

    assert rep.count == 1
    b = rep.budgets[0]
    assert b.breached is True and b.forecast_breach is True
    assert b.pct_used == 150.0 and b.forecast_pct == 200.0
