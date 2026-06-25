"""Deterministic intent router.

Classifies a question to a specialist with rules (no LLM), then forwards it to that specialist
— a remote A2A sub-agent if its URL is configured, else the in-process agent. This removes the
orchestrator-LLM's routing unreliability (e.g. budget questions deflecting) while still letting
the specialist's own (temperature-0) agent produce the answer from its tools.
"""
from __future__ import annotations

import os
from typing import Optional

from finops_core.config import Config

# Checked in order; first match wins. Anomaly/budget is most specific, then optimization,
# then cost is the default.
ANOMALY_KW = (
    "budget", "over budget", "over-budget", "breach", "anomaly", "anomalies", "spike",
    "spikes", "unusual", "unexpected", "overspend", "exceed",
)
OPTIMIZE_KW = (
    "saving", "save money", "save on", "reduce", "cut cost", "cut my", "cut the", "rightsiz",
    "right-siz", "idle", "reserved instance", "savings plan", "optimi", "wasted", "waste",
    "underutil", "over-provision", "overprovision", "recommend", "cheaper", "lower my", "trim",
)

_ENV = {
    "cost": "FINOPS_COST_AGENT_URL",
    "optimize": "FINOPS_OPTIMIZE_AGENT_URL",
    "anomaly": "FINOPS_ANOMALY_AGENT_URL",
}


def classify(question: str) -> str:
    """Map a question to 'cost' | 'optimize' | 'anomaly' deterministically."""
    q = question.lower()
    if any(k in q for k in ANOMALY_KW):
        return "anomaly"
    if any(k in q for k in OPTIMIZE_KW):
        return "optimize"
    return "cost"


def _text(result) -> str:
    msg = getattr(result, "message", None)
    if isinstance(msg, dict):
        parts = [p.get("text", "") for p in msg.get("content", []) if isinstance(p, dict)]
        if any(parts):
            return "".join(parts).strip()
    return str(result).strip()


class IntentRouter:
    def __init__(self, cfg: Optional[Config] = None, session=None):
        self.cfg = cfg or Config.load()
        self.session = session
        self.last_usage: Optional[dict] = None  # token/$ of the last in-process agent call

    def _local_agent(self, intent: str, hooks=None):
        if intent == "optimize":
            from finops_core.agents.optimize import build_optimize_agent
            return build_optimize_agent(self.session, self.cfg, callback_handler=None, hooks=hooks)
        if intent == "anomaly":
            from finops_core.agents.anomaly import build_anomaly_agent
            return build_anomaly_agent(self.session, self.cfg, callback_handler=None, hooks=hooks)
        from finops_core.agents.cost import build_cost_agent
        return build_cost_agent(self.session, self.cfg, callback_handler=None, hooks=hooks)

    def answer(self, question: str) -> tuple[str, str]:
        """Return (intent, answer_text). Uses the remote A2A specialist if its URL is set.
        For in-process calls, records token/$ usage in self.last_usage."""
        from finops_core.telemetry import traced
        intent = classify(question)
        self.last_usage = None
        # Span carries only metadata (intent / routing), never the question text or any figures.
        with traced("finops.route.answer", **{"finops.intent": intent}) as span:
            url = os.getenv(_ENV[intent])
            if url:
                from strands.agent.a2a_agent import A2AAgent
                if span is not None:
                    span.set_attribute("finops.route", "a2a")
                return intent, _text(A2AAgent(endpoint=url)(question))

            from finops_core.hooks import ToolMeter, default_hooks
            meter = ToolMeter()
            result = self._local_agent(intent, hooks=default_hooks(self.cfg, meter))(question)
            self._record_usage(result, intent, meter)
            if span is not None and self.last_usage:
                span.set_attribute("finops.tool_calls", self.last_usage.get("tools", {}).get("tool_calls", 0))
            return intent, _text(result)

    def structured_answer(self, question: str):
        """Return (intent, FinOpsAnswer | dict) — figures as typed fields (exact, from tools).
        In-process only; a remote A2A specialist returns text wrapped in a headline."""
        from finops_core.schemas.answer import FinOpsAnswer

        intent = classify(question)
        self.last_usage = None
        url = os.getenv(_ENV[intent])
        if url:
            from strands.agent.a2a_agent import A2AAgent
            return intent, {"headline": _text(A2AAgent(endpoint=url)(question)),
                            "figures": [], "remote": True}

        from finops_core.hooks import ToolMeter, default_hooks
        meter = ToolMeter()
        result = self._local_agent(intent, hooks=default_hooks(self.cfg, meter))(
            question, structured_output_model=FinOpsAnswer)
        self._record_usage(result, intent, meter)
        return intent, result.structured_output

    def _record_usage(self, result, intent: str, meter) -> None:
        try:
            from finops_core.models.router import ModelRouter
            from finops_core.pricing import usage_summary
            role = "optimization" if intent == "optimize" else "cost"
            usage = getattr(getattr(result, "metrics", None), "accumulated_usage", None)
            self.last_usage = {
                **usage_summary(ModelRouter(self.cfg).model_id(role), dict(usage or {})),
                "tools": meter.summary(),
            }
            from finops_core.telemetry import record_llm_usage
            record_llm_usage(self.last_usage)  # OTEL token + estimated-$ metrics
        except Exception:
            self.last_usage = None
