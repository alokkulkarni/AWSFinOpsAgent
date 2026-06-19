"""Scheduled digest workflow — a parallel DAG that gathers cost/anomaly/optimization data
(deterministically) and renders a report, with optional LLM narrative and delivery adapters."""

from finops_core.workflow.digest import build_digest, gather  # noqa: F401
