"""Observability: an AWS-API meter (botocore hook) that counts calls and estimates the
Cost-Explorer spend the agent itself incurs ($0.01/request), plus structured-logging setup.
"""
from __future__ import annotations

import logging
import sys

# Cost Explorer requests are billed ~$0.01 each — the one AWS API where the agent's own usage
# has a non-trivial cost, so we surface it.
_CE_REQUEST_USD = 0.01
_CE_SERVICES = {"ce", "cost-explorer"}


class ApiMeter:
    def __init__(self):
        self.calls: dict[str, int] = {}

    def record(self, service: str, operation: str) -> None:
        self.calls[f"{service}:{operation}"] = self.calls.get(f"{service}:{operation}", 0) + 1

    def _handler(self, model=None, **kwargs) -> None:
        if model is None:
            return
        try:
            service = model.service_model.service_name
            self.record(service, model.name)
        except Exception:
            pass

    def instrument(self, session) -> "ApiMeter":
        """Register an after-call hook on a boto3/botocore session (applies to all its clients)."""
        bc = getattr(session, "_session", session)  # boto3.Session wraps a botocore Session
        try:
            bc.register("after-call", self._handler)
        except Exception:
            pass
        return self

    def summary(self) -> dict:
        total = sum(self.calls.values())
        ce_calls = sum(v for k, v in self.calls.items() if k.split(":", 1)[0] in _CE_SERVICES)
        return {
            "api_calls": total,
            "ce_requests": ce_calls,
            "estimated_ce_cost_usd": round(ce_calls * _CE_REQUEST_USD, 2),
            "by_operation": dict(sorted(self.calls.items(), key=lambda kv: -kv[1])),
        }


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("finops")
    if not logger.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s finops %(message)s"))
        logger.addHandler(h)
    logger.setLevel(level.upper())
    return logger
