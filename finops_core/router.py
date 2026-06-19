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

    def _local_agent(self, intent: str):
        if intent == "optimize":
            from finops_core.agents.optimize import build_optimize_agent
            return build_optimize_agent(self.session, self.cfg, callback_handler=None)
        if intent == "anomaly":
            from finops_core.agents.anomaly import build_anomaly_agent
            return build_anomaly_agent(self.session, self.cfg, callback_handler=None)
        from finops_core.agents.cost import build_cost_agent
        return build_cost_agent(self.session, self.cfg, callback_handler=None)

    def answer(self, question: str) -> tuple[str, str]:
        """Return (intent, answer_text). Uses the remote A2A specialist if its URL is set."""
        intent = classify(question)
        url = os.getenv(_ENV[intent])
        if url:
            from strands.agent.a2a_agent import A2AAgent
            return intent, _text(A2AAgent(endpoint=url)(question))
        return intent, _text(self._local_agent(intent)(question))
