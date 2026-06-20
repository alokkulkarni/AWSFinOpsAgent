"""Typed FinOps answer schema for Strands structured output.

When an agent is invoked with structured_output_model=FinOpsAnswer, the model returns figures as
typed fields (sourced verbatim from tool results) instead of free prose — so API/dashboard
consumers and the orchestrator get machine-readable EXACT numbers, not paraphrased text.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Figure(BaseModel):
    label: str = Field(description="What this figure is (a service, account, budget, finding, ...)")
    amount: float = Field(description="The exact amount, copied verbatim from a tool result")
    unit: str = Field(default="USD", description="Currency or unit")
    pct: Optional[float] = Field(default=None, description="Percent of total, if applicable")


class FinOpsAnswer(BaseModel):
    headline: str = Field(description="One-line answer with the key number")
    period: Optional[str] = Field(default=None, description="Period used, e.g. mtd, last_month, 3m")
    metric: Optional[str] = Field(default=None, description="Cost metric, e.g. UnblendedCost")
    figures: list[Figure] = Field(default_factory=list, description="Exact figures from tools")
    note: Optional[str] = Field(default=None, description="Caveats — e.g. estimated, not enrolled")
