---
name: anomaly-triage
description: Triage AWS cost anomalies and budget breaches — rank by impact, find the root-cause dimension, and separate real anomalies from forecast noise. Use for "is anything wrong?" questions.
allowed-tools: read_skill_file
metadata:
  version: "1.0"
---
# Anomaly & budget triage

Use when the user asks "is anything wrong?", about cost anomalies, or about budget / forecast breaches.

## Procedure
1. `get_cost_anomalies` for the window; rank by **total impact**, not count. A cluster of tiny
   anomalies on one service often matters less than a single large one.
2. For each top anomaly, attribute the spend with `drill_down` on the implicated service to find the
   dimension (usage type / region / account) that actually moved.
3. `get_budgets_status` — flag budgets where **actual OR forecast** breaches the limit; state which.
4. Distinguish a real step-change from forecast noise: a forecast breach with flat actuals is a
   watch item, not an incident.

## Rules
- Report impact figures and breach thresholds exactly as the tools return them.
- Always name the root-cause dimension you found — not just "EC2 went up".
- If no anomaly monitors exist, say detection isn't configured rather than implying "all clear".
