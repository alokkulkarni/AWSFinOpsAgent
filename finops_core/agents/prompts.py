"""System prompts (steering) for the FinOps agents.

The actual text lives in versioned Markdown playbooks under finops_core/steering/ so it can be
reviewed/edited like docs. These constants keep the existing import surface stable.
"""
from finops_core.steering import load_steering

ORCHESTRATOR_PROMPT = load_steering("orchestrator")
COST_ANALYSIS_PROMPT = load_steering("cost")
OPTIMIZATION_PROMPT = load_steering("optimization")
ANOMALY_PROMPT = load_steering("anomaly")
