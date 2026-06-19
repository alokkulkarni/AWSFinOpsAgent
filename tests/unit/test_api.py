import pytest

pytest.importorskip("fastapi")

import boto3  # noqa: E402
from botocore.stub import Stubber  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from apps.api.main import app, get_cost_explorer  # noqa: E402
from finops_core.cost.explorer import CostExplorer  # noqa: E402


def test_healthz():
    with TestClient(app) as c:
        r = c.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_config_redacted():
    with TestClient(app) as c:
        r = c.get("/config")
    assert r.status_code == 200 and "mode" in r.json() and "llm" in r.json()


def test_cost_by_service_endpoint_uses_tool_layer():
    client = boto3.client("ce", region_name="us-east-1",
                          aws_access_key_id="x", aws_secret_access_key="y", aws_session_token="z")
    stub = Stubber(client)
    stub.add_response("get_cost_and_usage", {"ResultsByTime": [{
        "TimePeriod": {"Start": "2026-06-01", "End": "2026-06-19"}, "Estimated": False, "Total": {},
        "Groups": [
            {"Keys": ["Amazon EC2"], "Metrics": {"UnblendedCost": {"Amount": "40.0", "Unit": "USD"}}},
            {"Keys": ["Amazon S3"], "Metrics": {"UnblendedCost": {"Amount": "10.0", "Unit": "USD"}}},
        ]}]})
    stub.activate()
    app.dependency_overrides[get_cost_explorer] = lambda: CostExplorer(ce_client=client)
    try:
        with TestClient(app) as c:
            r = c.get("/cost/by-service", params={"period": "mtd", "top_n": 10})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 50.0
        assert data["groups"][0]["key"] == "Amazon EC2"
    finally:
        app.dependency_overrides.clear()
