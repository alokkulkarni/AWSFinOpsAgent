---
name: savings-plan-vs-ri
description: Decide between Savings Plans and Reserved Instances and read the recommendation tools correctly (term, payment option, lookback, coverage, break-even). Use for commitment-discount questions.
allowed-tools: read_skill_file
metadata:
  version: "1.0"
---
# Savings Plans vs Reserved Instances

Use when the user asks about commitment-based discounts. This skill is the **decision
procedure**, not the figures — pull every number from the tools.

## Decide the instrument
- Heterogeneous / changing compute (mix of instance families, Fargate, Lambda) → **Compute Savings Plan**.
- Stable, specific usage you won't change → **EC2 Instance SP** or **Standard RI** (deepest discount,
  least flexible).
- Need capacity guarantee in an AZ → **zonal RI** (capacity), otherwise regional.

## Read the recommendations
1. `get_savings_plans_recommendations(term, payment, lookback)` and
   `get_reservation_recommendations(service, term, payment)` — compare estimated savings AND utilization.
2. Vary `lookback` (e.g. 7 / 30 / 60 days). A recommendation that collapses on a longer lookback is noise.
3. Check existing coverage/utilization first (`get_savings_plans_coverage_utilization`,
   `get_reservation_coverage_utilization`) — don't recommend buying into already-covered usage.

## Rank
Rank by net monthly savings, then by flexibility / effort / risk. Read `references/breakeven.md`
for the payment-option and break-even rule of thumb before recommending All-Upfront or a 3-year term.
