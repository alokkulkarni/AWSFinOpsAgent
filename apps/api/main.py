"""FastAPI gateway.

Deterministic data endpoints (/cost, /optimize, /anomalies, /budgets) return exact figures
straight from the tool layer. /query routes the question deterministically (IntentRouter) to a
specialist. Dependencies are injectable so the endpoints are testable with a stubbed client.

Run: uvicorn apps.api.main:app --port 8000   (or: make api).  Docs at /docs.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from finops_core.anomaly.engine import AnomalyEngine
from finops_core.config import Config
from finops_core.cost.explorer import CostExplorer
from finops_core.optimize.engine import Optimizer

app = FastAPI(
    title="AWS FinOps Agent API",
    version="0.1.0",
    summary="Deterministic AWS cost data + intent-routed FinOps chat.",
)


# ---- dependencies (override in tests) -------------------------------------
@lru_cache
def get_config() -> Config:
    return Config.load()


from finops_core.observe import ApiMeter  # noqa: E402

_meter = ApiMeter()


@lru_cache
def get_session():
    from finops_core.aws.session import build_session
    session = build_session(get_config())
    _meter.instrument(session)  # count AWS API calls + estimate CE spend
    return session


def get_cost_explorer() -> CostExplorer:
    return CostExplorer(get_session(), get_config())


def get_optimizer() -> Optimizer:
    return Optimizer(get_session(), get_config())


def get_anomaly() -> AnomalyEngine:
    return AnomalyEngine(get_session(), get_config())


# ---- models ----------------------------------------------------------------
class DrillRequest(BaseModel):
    group_by: str = "SERVICE"
    filters: dict = {}
    period: str = "mtd"
    metric: str = "UnblendedCost"
    top_n: int = 15


class QueryRequest(BaseModel):
    question: str
    structured: bool = False   # return typed figures (FinOpsAnswer) instead of prose


class DigestRequest(BaseModel):
    format: str = "md"
    narrative: bool = False


class FixRequest(BaseModel):
    finding: dict
    format: str = "cli"


class PreviewRequest(BaseModel):
    action_id: str
    params: dict = {}


class ApplyRequest(BaseModel):
    action_id: str
    token: str
    params: dict = {}


# ---- meta ------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/config")
def config(cfg: Config = Depends(get_config)):
    return cfg.redacted()


@app.get("/metrics")
def metrics():
    """AWS API call counts + estimated Cost Explorer spend incurred by this process."""
    return _meter.summary()


# ---- cost ------------------------------------------------------------------
@app.get("/cost/summary")
def cost_summary(period: str = "mtd", granularity: str = "MONTHLY",
                 metric: str = "UnblendedCost", ce: CostExplorer = Depends(get_cost_explorer)):
    return ce.summary(period=period, granularity=granularity, metric=metric).to_dict()


@app.get("/cost/by-service")
def cost_by_service(period: str = "mtd", top_n: int = 10, granularity: str = "MONTHLY",
                    metric: str = "UnblendedCost", ce: CostExplorer = Depends(get_cost_explorer)):
    return ce.cost_by_service(period=period, top_n=top_n, granularity=granularity,
                              metric=metric).to_dict()


@app.get("/cost/by-account")
def cost_by_account(period: str = "mtd", top_n: int = 20, metric: str = "UnblendedCost",
                    ce: CostExplorer = Depends(get_cost_explorer)):
    b = ce.cost_by_account(period=period, top_n=top_n, metric=metric).to_dict()
    try:
        from finops_core.aws.org import OrgResolver
        return OrgResolver(get_session(), get_config()).enrich_breakdown(b)
    except Exception:
        return b


@app.get("/accounts")
def accounts_list():
    from finops_core.aws.org import OrgResolver
    return OrgResolver(get_session(), get_config()).list_accounts()


@app.post("/cost/drilldown")
def cost_drilldown(req: DrillRequest, ce: CostExplorer = Depends(get_cost_explorer)):
    return ce.drill_down(req.group_by, req.filters, period=req.period,
                         metric=req.metric, top_n=req.top_n).to_dict()


@app.get("/cost/trend")
def cost_trend(months: int = 6, metric: str = "UnblendedCost",
               ce: CostExplorer = Depends(get_cost_explorer)):
    return ce.trend(months=months, metric=metric).to_dict()


@app.get("/cost/forecast")
def cost_forecast(horizon: str = "eom", metric: str = "UnblendedCost",
                  ce: CostExplorer = Depends(get_cost_explorer)):
    return ce.forecast(horizon=horizon, metric=metric).to_dict()


# ---- optimize / anomaly / budgets -----------------------------------------
@app.get("/optimize/recommendations")
def optimize_recommendations(opt: Optimizer = Depends(get_optimizer)):
    return opt.all_recommendations().to_dict()


@app.get("/anomalies")
def anomalies(period: str = "30d", eng: AnomalyEngine = Depends(get_anomaly)):
    return eng.anomalies(period=period).to_dict()


@app.get("/budgets")
def budgets(eng: AnomalyEngine = Depends(get_anomaly)):
    return eng.budgets().to_dict()


# ---- intent-routed chat ----------------------------------------------------
@app.post("/report/digest")
def report_digest(req: DigestRequest, cfg: Config = Depends(get_config)):
    from finops_core.workflow.digest import build_digest
    report = build_digest(cfg, get_session(), fmt=req.format, with_narrative=req.narrative)
    return {"format": req.format, "report": report}


@app.post("/query")
def query(req: QueryRequest, cfg: Config = Depends(get_config)):
    try:
        from finops_core.router import IntentRouter
        router = IntentRouter(cfg, get_session())
        if req.structured:
            intent, ans = router.structured_answer(req.question)
            payload = ans.model_dump() if hasattr(ans, "model_dump") else ans
            return {"intent": intent, "structured": payload, "usage": router.last_usage}
        intent, answer = router.answer(req.question)
        return {"intent": intent, "answer": answer, "usage": router.last_usage}
    except ImportError:
        return {"error": "agent extra not installed (pip install -e '.[agent]')"}


# ---- remediation (mode-gated) ---------------------------------------------
@app.post("/fix")
def fix(req: FixRequest, cfg: Config = Depends(get_config)):
    from finops_core.modes import can_generate_artifacts
    if not can_generate_artifacts(cfg.mode):
        raise HTTPException(403, "artifact generation needs artifacts or guarded_write mode")
    from finops_core.remediation.artifacts import generate_artifact
    return generate_artifact(req.finding, req.format).to_dict()


@app.get("/actions")
def actions(cfg: Config = Depends(get_config)):
    from finops_core.remediation.actions import RemediationEngine
    return {"mode": cfg.mode, "actions": [a.to_dict() for a in RemediationEngine(cfg).list_actions()]}


@app.post("/actions/preview")
def actions_preview(req: PreviewRequest, cfg: Config = Depends(get_config)):
    from finops_core.remediation.actions import ModeError, RemediationEngine
    try:
        return RemediationEngine(cfg, get_session()).preview(req.action_id, req.params).to_dict()
    except ModeError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/actions/apply")
def actions_apply(req: ApplyRequest, cfg: Config = Depends(get_config)):
    from finops_core.remediation.actions import ModeError, RemediationEngine
    try:
        return RemediationEngine(cfg, get_session()).apply(req.action_id, req.token, req.params).to_dict()
    except ModeError as e:
        raise HTTPException(403, str(e))
