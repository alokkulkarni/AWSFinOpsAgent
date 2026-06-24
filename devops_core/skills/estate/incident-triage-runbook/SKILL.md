---
name: incident-triage-runbook
description: Structured first-pass triage of an AWS estate incident — scope blast radius, correlate recent changes, and propose a posture-shaped, read-only diagnosis before any fix. Use when a user reports something broken or degraded.
allowed-tools: read_skill_file
metadata:
  version: "1.0"
---
# Incident triage runbook (read-only first)

Use when the user reports a failure, outage, or degradation in the AWS estate. Stay read-only:
propose fixes, never apply them here.

## Procedure
1. **Scope** — identify the affected component(s) and their dependencies from the estate index
   before theorizing. Blast radius first.
2. **Correlate** — look for recent changes (deploys, scaling, config) around the onset window.
3. **Localize** — use the diagnose/review tools to gather signals (health, errors, limits) for the
   suspect resources; cite each signal.
4. **Root-cause** — state the most likely cause and the evidence for it; note what would confirm or
   refute it.
5. **Fix proposal** — describe the minimal posture-appropriate change, then stop. Application is a
   separate, human-confirmed step.

## Rules
- Cite the resource/signal behind every claim; no unsourced assertions.
- Prefer the narrowest explanation that fits the evidence.
- Never recommend a destructive or write action without flagging it as guarded / confirmation-required.
