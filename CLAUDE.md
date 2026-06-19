# CLAUDE.md — AWS FinOps Agent

AI FinOps agent (Strands Agents SDK + Amazon Bedrock) that analyzes AWS cost using the
user's local credentials. **Read `SPEC.md` before any non-trivial work** — it's the source of truth.

## Golden rules (non-negotiable)
- **Every change ships as a PR.** Always work on a feature branch (`phase-N/...` or
  `feat/...`), never commit to `main` directly. **Commit and merge ONLY after explicit
  user confirmation** — propose the diff, wait for the OK.
- **Never commit secrets.** No AWS keys, `.env`, `~/.aws`, session tokens, account IDs, or
  customer/billing data in git. Inspect `git diff --staged` before every commit and keep
  `.gitignore` current.
- **Read-only by default.** Agent defaults to `advisory` mode. Write actions are opt-in
  (`guarded_write`), allowlisted, dry-run previewed, and require human confirmation.
- **Numbers must be exact.** Agent answers must match Cost Explorer / CUR — never LLM-estimated.

## Architecture (one breath)
One shared **tool layer** (deterministic boto3 wrappers) is exposed BOTH directly to the UI
(fast path, no LLM) AND as Strands `@tool`s to a hierarchical **orchestrator + specialist
sub-agents** (Cost-Analysis, Optimization, Anomaly/Forecast, CUR/Athena, Account/Org).
Scheduled digest = Strands **Workflow** DAG. Streamlit dashboard + FastAPI over `finops_core`.

## Layout
- `finops_core/` — `aws/` sessions+identity, `models/` router, `tools/`, `agents/`, `workflow/`, `schemas/`
- `apps/dashboard/` (Streamlit) · `apps/api/` (FastAPI)
- `config/` finops.yaml + models.yaml · `iam/` policies · `tests/`

## Conventions
- Python 3.11+, type hints, dataclasses for normalized results. boto3 with adaptive retries + pagination.
- Cost Explorer & Budgets clients use region `us-east-1`. Cache CE/Athena responses (TTL) — billed per call.
- Models resolved via `ModelRouter` (Bedrock; Claude Sonnet default, env-switchable to Nova Pro/Haiku).
  **Never hardcode model IDs** — use `config/models.yaml`.
- Tool wrappers stay thin/typed — one AWS concern each; the same function serves UI and agent.
- Config via `config/*.yaml` with env overrides (`FINOPS_*`, standard `AWS_*`). Env wins.

## Commands
- `make install` · `make preflight` (STS identity + Bedrock check) · `make whoami`
- `make docker-preflight` · `make sandbox-preflight` · `make dashboard` · `make api`

## Per-task workflow
1. Branch. 2. Implement + add/adjust tests. 3. Show diff + summary.
4. Ask to commit. 5. On confirm: commit (with the Co-Authored-By sign-off), open PR.
6. Merge only on explicit user OK. Update `SPEC.md` when scope changes.
