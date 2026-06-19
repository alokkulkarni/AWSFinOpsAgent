"""Deterministic optimization engine. Each source is wrapped defensively and degrades to a
note (instead of failing) when it isn't enrolled / lacks support entitlement / has no data.

Sources: CE rightsizing, Compute Optimizer, CE Savings Plans + Reservation recs, Cost
Optimization Hub, Trusted Advisor cost checks.
"""
from __future__ import annotations

from typing import Optional

from finops_core.aws.session import client
from finops_core.config import Config
from finops_core.schemas.optimize import OptimizationReport, Recommendation

_UNAVAILABLE = (
    "OptInRequired", "SubscriptionRequired", "AccessDenied", "AccessDeniedException",
    "not enrolled", "NotEnrolled", "ResourceNotFound", "DataUnavailable",
)


def _money(x) -> float:
    """Coerce the many AWS money shapes ({'Amount': '1.2'} | {'value': 1.2} | '1.2' | 1.2)."""
    if x is None:
        return 0.0
    if isinstance(x, dict):
        for k in ("Amount", "value", "Value", "EstimatedMonthlySavingsAmount"):
            if k in x:
                return _money(x[k])
        return 0.0
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _unavailable_reason(err: Exception) -> Optional[str]:
    msg = str(err)
    return next((m for m in _UNAVAILABLE if m.lower() in msg.lower()), None)


class Optimizer:
    def __init__(self, session=None, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self.session = session

    def _client(self, service: str, region: Optional[str] = None):
        if self.session is None:  # build lazily so Optimizer(cfg=...) works standalone
            from finops_core.aws.session import build_session
            self.session = build_session(self.cfg)
        return client(self.session, service, region=region)

    # ---- individual sources (each returns (recs, notes)) --------------
    def rightsizing(self, service: str = "AmazonEC2"):
        recs, notes = [], []
        try:
            ce = self._client("ce", self.cfg.aws.ce_region)
            token = None
            while True:
                kw = {"Service": service,
                      "Configuration": {"RecommendationTarget": "SAME_INSTANCE_FAMILY",
                                        "BenefitsConsidered": True}}
                if token:
                    kw["NextPageToken"] = token
                resp = ce.get_rightsizing_recommendation(**kw)
                for r in resp.get("RightsizingRecommendations", []):
                    cur = r.get("CurrentInstance", {})
                    rtype = r.get("RightsizingType", "MODIFY")
                    if rtype == "TERMINATE":
                        save = _money(r.get("TerminateRecommendationDetail", {}).get("EstimatedMonthlySavings"))
                        recommended = "Terminate (idle)"
                    else:
                        targets = r.get("ModifyRecommendationDetail", {}).get("TargetInstances", [])
                        best = max(targets, key=lambda t: _money(t.get("EstimatedMonthlySavings")), default={})
                        save = _money(best.get("EstimatedMonthlySavings"))
                        recommended = (best.get("ResourceDetails", {})
                                       .get("EC2ResourceDetails", {}).get("InstanceType", "smaller instance"))
                    recs.append(Recommendation(
                        source="rightsizing", category=("idle" if rtype == "TERMINATE" else "rightsize"),
                        title=f"Rightsize EC2 {cur.get('ResourceId', '')}".strip(),
                        monthly_savings=round(save, 2),
                        resource_id=cur.get("ResourceId"), resource_type="ec2-instance",
                        account=r.get("AccountId"),
                        current=cur.get("ResourceDetails", {}).get("EC2ResourceDetails", {}).get("InstanceType"),
                        recommended=recommended, effort="medium",
                        risk=("medium" if rtype == "MODIFY" else "high"),
                        rationale="Cost Explorer rightsizing recommendation.",
                        action=rtype.lower(),
                    ))
                token = resp.get("NextPageToken")
                if not token:
                    break
        except Exception as e:
            notes.append(f"rightsizing: {_unavailable_reason(e) or e}")
        return recs, notes

    def compute_optimizer(self):
        recs, notes = [], []
        getters = {
            "ec2-instance": ("get_ec2_instance_recommendations", "instanceRecommendations",
                             "currentInstanceType", "instanceArn"),
            "ebs-volume": ("get_ebs_volume_recommendations", "volumeRecommendations",
                           "currentConfiguration", "volumeArn"),
            "lambda-function": ("get_lambda_function_recommendations", "lambdaFunctionRecommendations",
                                "currentMemorySize", "functionArn"),
        }
        try:
            co = self._client("compute-optimizer", self.cfg.aws.region)
        except Exception as e:
            return recs, [f"compute-optimizer: {e}"]
        for rtype, (method, key, cur_field, arn_field) in getters.items():
            try:
                resp = getattr(co, method)()
                for r in resp.get(key, []):
                    options = r.get("recommendationOptions", [])
                    best = max(options,
                               key=lambda o: _money(o.get("savingsOpportunity", {}).get("estimatedMonthlySavings")),
                               default={})
                    save = _money(best.get("savingsOpportunity", {}).get("estimatedMonthlySavings"))
                    finding = r.get("finding", "")
                    if save <= 0 and finding in ("Optimized", "NotOptimized", ""):
                        continue
                    recs.append(Recommendation(
                        source="compute-optimizer", category="rightsize",
                        title=f"Compute Optimizer: {rtype} {finding}".strip(),
                        monthly_savings=round(save, 2),
                        resource_id=r.get(arn_field), resource_type=rtype,
                        account=r.get("accountId"),
                        current=str(r.get(cur_field, "")),
                        recommended=str(best.get("instanceType") or best.get("memorySize") or "see option"),
                        effort="medium", risk="low" if finding == "Overprovisioned" else "medium",
                        rationale=f"Compute Optimizer finding: {finding}.",
                        action="rightsize",
                    ))
            except Exception as e:
                notes.append(f"compute-optimizer {rtype}: {_unavailable_reason(e) or e}")
        return recs, notes

    def savings_plans(self, term="ONE_YEAR", payment="NO_UPFRONT", lookback="THIRTY_DAYS"):
        recs, notes = [], []
        try:
            ce = self._client("ce", self.cfg.aws.ce_region)
            resp = ce.get_savings_plans_purchase_recommendation(
                SavingsPlansType="COMPUTE_SP", TermInYears=term,
                PaymentOption=payment, LookbackPeriodInDays=lookback)
            summary = (resp.get("SavingsPlansPurchaseRecommendation", {})
                       .get("SavingsPlansPurchaseRecommendationSummary", {}))
            save = _money(summary.get("EstimatedMonthlySavingsAmount"))
            if save > 0:
                recs.append(Recommendation(
                    source="savings-plans", category="commitment",
                    title="Purchase a Compute Savings Plan",
                    monthly_savings=round(save, 2),
                    recommended=f"{summary.get('HourlyCommitmentToPurchase', '?')}/hr commitment, {term}",
                    effort="low", risk="low",
                    rationale=f"Based on last {lookback.replace('_', ' ').lower()} of usage "
                              f"({summary.get('EstimatedSavingsPercentage', '?')}% est. savings).",
                    action="purchase-savings-plan",
                ))
        except Exception as e:
            notes.append(f"savings-plans: {_unavailable_reason(e) or e}")
        return recs, notes

    def reservations(self, service="Amazon Elastic Compute Cloud - Compute",
                     term="ONE_YEAR", payment="NO_UPFRONT", lookback="THIRTY_DAYS"):
        recs, notes = [], []
        try:
            ce = self._client("ce", self.cfg.aws.ce_region)
            resp = ce.get_reservation_purchase_recommendation(
                Service=service, TermInYears=term, PaymentOption=payment,
                LookbackPeriodInDays=lookback)
            for rec in resp.get("Recommendations", []):
                summary = rec.get("RecommendationSummary", {})
                save = _money(summary.get("TotalEstimatedMonthlySavingsAmount"))
                if save > 0:
                    recs.append(Recommendation(
                        source="reservations", category="commitment",
                        title=f"Purchase Reserved Instances ({service})",
                        monthly_savings=round(save, 2),
                        recommended=f"{term} {payment}",
                        effort="low", risk="medium",
                        rationale=f"{summary.get('TotalEstimatedMonthlySavingsPercentage', '?')}% est. savings.",
                        action="purchase-ri",
                    ))
        except Exception as e:
            notes.append(f"reservations: {_unavailable_reason(e) or e}")
        return recs, notes

    def cost_optimization_hub(self):
        recs, notes = [], []
        try:
            coh = self._client("cost-optimization-hub", "us-east-1")
            paginator = coh.get_paginator("list_recommendations")
            for page in paginator.paginate():
                for r in page.get("items", []):
                    save = _money(r.get("estimatedMonthlySavings"))
                    recs.append(Recommendation(
                        source="cost-optimization-hub",
                        category=(r.get("actionType", "other") or "other").lower(),
                        title=f"{r.get('actionType', 'Optimize')} {r.get('currentResourceType', '')}".strip(),
                        monthly_savings=round(save, 2),
                        resource_id=r.get("resourceId"), resource_type=r.get("currentResourceType"),
                        account=r.get("accountId"), region=r.get("region"),
                        effort="medium", risk="low",
                        rationale="AWS Cost Optimization Hub (unified) recommendation.",
                        action=(r.get("actionType", "") or "").lower(),
                    ))
        except Exception as e:
            notes.append(f"cost-optimization-hub: {_unavailable_reason(e) or e}")
        return recs, notes

    def trusted_advisor_cost(self):
        recs, notes = [], []
        try:
            sup = self._client("support", "us-east-1")  # Support API is us-east-1 only
            checks = sup.describe_trusted_advisor_checks(language="en").get("checks", [])
            cost_checks = [c for c in checks if c.get("category") == "cost_optimizing"]
            for c in cost_checks:
                try:
                    res = sup.describe_trusted_advisor_check_result(
                        checkId=c["id"], language="en").get("result", {})
                except Exception:
                    continue
                if res.get("status") not in ("warning", "error"):
                    continue
                save = _money(res.get("categorySpecificSummary", {})
                              .get("costOptimizing", {}).get("estimatedMonthlySavings"))
                flagged = res.get("resourcesSummary", {}).get("resourcesFlagged", 0)
                recs.append(Recommendation(
                    source="trusted-advisor", category="cleanup",
                    title=f"Trusted Advisor: {c.get('name', '')}",
                    monthly_savings=round(save, 2),
                    effort="low", risk="low",
                    rationale=f"{flagged} flagged resource(s); status={res.get('status')}.",
                    action="review",
                ))
        except Exception as e:
            notes.append(f"trusted-advisor: {_unavailable_reason(e) or e} (needs Business/Enterprise Support)")
        return recs, notes

    # ---- aggregate ----------------------------------------------------
    def all_recommendations(self) -> OptimizationReport:
        all_recs, notes = [], []
        for fn in (self.rightsizing, self.compute_optimizer, self.savings_plans,
                   self.reservations, self.cost_optimization_hub, self.trusted_advisor_cost):
            recs, ns = fn()
            all_recs.extend(recs)
            notes.extend(ns)

        # dedup: keep highest savings per key
        best: dict = {}
        for r in all_recs:
            k = r.key()
            if k not in best or r.monthly_savings > best[k].monthly_savings:
                best[k] = r
        deduped = sorted(best.values(), key=lambda r: r.monthly_savings, reverse=True)

        by_source: dict = {}
        for r in deduped:
            by_source[r.source] = by_source.get(r.source, 0) + 1
        currency = deduped[0].currency if deduped else "USD"
        total = round(sum(r.monthly_savings for r in deduped), 2)
        return OptimizationReport(total, currency, len(deduped), by_source, deduped, notes)
