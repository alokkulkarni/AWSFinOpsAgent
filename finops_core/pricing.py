"""Rough Bedrock on-demand price estimates so the agent can report the LLM spend it incurs
(FinOps-on-itself). USD per 1K tokens, us-east-1 — ESTIMATES; verify at
https://aws.amazon.com/bedrock/pricing/. Matched by substring on the model id.
"""
from __future__ import annotations

# per 1K tokens
BEDROCK_PRICES = {
    "claude-sonnet": {"input": 0.003, "output": 0.015, "cache_read": 0.0003, "cache_write": 0.00375},
    "claude-haiku":  {"input": 0.001, "output": 0.005, "cache_read": 0.0001, "cache_write": 0.00125},
    "nova-pro":      {"input": 0.0008, "output": 0.0032, "cache_read": 0.0002, "cache_write": 0.001},
    "nova-lite":     {"input": 0.00006, "output": 0.00024},
    "nova-micro":    {"input": 0.000035, "output": 0.00014},
}
_DEFAULT = {"input": 0.003, "output": 0.015, "cache_read": 0.0003, "cache_write": 0.00375}


def _price_for(model_id: str) -> dict:
    mid = (model_id or "").lower()
    for key, price in BEDROCK_PRICES.items():
        if key in mid:
            return price
    return _DEFAULT


def estimate_cost(model_id: str, input_tokens: int = 0, output_tokens: int = 0,
                  cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float:
    p = _price_for(model_id)
    usd = (
        input_tokens * p["input"]
        + output_tokens * p["output"]
        + cache_read_tokens * p.get("cache_read", p["input"])
        + cache_write_tokens * p.get("cache_write", p["input"])
    ) / 1000.0
    return round(usd, 6)


def usage_summary(model_id: str, accumulated_usage: dict | None) -> dict:
    """Normalize Strands/Bedrock accumulated_usage into counts + an estimated $."""
    u = accumulated_usage or {}
    inp = int(u.get("inputTokens", 0) or 0)
    out = int(u.get("outputTokens", 0) or 0)
    cr = int(u.get("cacheReadInputTokens", 0) or 0)
    cw = int(u.get("cacheWriteInputTokens", 0) or 0)
    return {
        "model": model_id,
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_tokens": cr,
        "cache_write_tokens": cw,
        "estimated_usd": estimate_cost(model_id, inp, out, cr, cw),
    }
