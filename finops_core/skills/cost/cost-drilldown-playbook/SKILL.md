---
name: cost-drilldown-playbook
description: Methodology for double-click drill-down of AWS spend (service to usage type to operation to region to linked account to resource) using the cost tools. Use when a user asks where money is going or to explain a spend spike.
allowed-tools: read_skill_file
metadata:
  version: "1.0"
---
# Cost drill-down playbook

When the user asks "where is my money going?" or "why did <service> jump?", drill in this
fixed order and stop once the cause is explained. Never guess a number — read every figure from
a tool.

## Procedure
1. Start broad: `get_cost_by_service` for the period; identify the top movers (largest Δ%).
2. Double-click the suspect service with `drill_down`, advancing **one dimension at a time**:
   `SERVICE → USAGE_TYPE → OPERATION → REGION → LINKED_ACCOUNT → RESOURCE_ID` (resource needs CUR).
3. At each level, compare the current period to the prior comparable period to localize the delta.
4. Stop at the first dimension that explains the bulk of the change; report the path you took.

## Rules
- Every figure you report MUST come from a tool call, verbatim — do not estimate or round silently.
- If a dimension isn't available (e.g. `RESOURCE_ID` without CUR), say so and stop at the deepest
  available level.
- Prefer the smallest period that answers the question to limit Cost Explorer spend (billed per call).
