# AWS FinOps Agent — Technical Specification

> **Status:** Draft v0.1 (spec-first; no code yet)
> **Owner:** Alok Kulkarni
> **Built with:** [Strands Agents SDK](https://strandsagents.com) (model-driven multi-agent framework)
> **Date:** 2026-06-19

---

## 1. Purpose & Vision

The **FinOps Agent** is an AI agent that connects to your AWS account(s) using your
local credentials and answers the core FinOps questions:

1. **What is my bill?** — total spend and trend over any period.
2. **Where is the money going?** — cost per service, ranked, with full drill-down
   ("double-click" any service → usage type → operation → region → resource → linked account).
3. **How do I spend less?** — concrete, prioritized optimization recommendations
   (rightsizing, Savings Plans / Reserved Instances, idle-resource cleanup, anomalies).
4. **Is anything wrong?** — cost anomalies, budget breaches, forecast overruns.

It runs locally (Docker + a hardened "sandbox" container profile), uses Amazon Bedrock
for reasoning (Claude Sonnet by default with model fallback), and exposes both a
**Streamlit dashboard** (visual, click-to-drill-down) and a **FastAPI REST service**
(headless / integration) over one shared agent core.

### Non-goals (v1)
- Not a replacement for AWS Cost Explorer / Billing console; it *orchestrates* those APIs.
- Not a continuous autonomous remediation system. Write actions are opt-in, allowlisted,
  and human-confirmed.
- No third-party cloud (GCP/Azure) cost. AWS only for v1.

---

## 2. Locked Decisions (from spec interview)

| Decision | Choice |
|---|---|
| **Model backend** | Amazon Bedrock with fallback: **Claude Sonnet 4.x default**, switchable via env to **Nova Pro** / **Claude Haiku** (cost/latency). Optional Anthropic-API path. |
| **Interfaces** | **Streamlit dashboard** *and* **FastAPI REST**, both over a shared agent/tool core. |
| **Data scope** | **Full** — Cost Explorer, CE rightsizing, Compute Optimizer, Cost Optimization Hub, Savings Plans / RI recs, **CUR via Athena**, Budgets, Cost Anomaly Detection, Trusted Advisor, Pricing, Free Tier. |
| **Account scope** | **Both** single account *and* AWS Organizations / consolidated billing with **per-linked-account** breakdown. |
| **Orchestration** | **Hybrid**: Agents-as-Tools hierarchical orchestrator (interactive) **+** a Strands **Workflow** DAG (scheduled digest). |
| **Action posture** | **User-selectable mode**: `advisory` (read-only) · `artifacts` (read-only + generate scripts/IaC) · `guarded_write` (allowlisted actions w/ human confirmation). |
| **CUR / Athena** | Agent can **provision** the Data Export + Athena workgroup + S3 (one-time guarded write); degrades gracefully to Cost Explorer if absent. |
| **Credentials in Docker** | **All configurable**: mounted `~/.aws` (read-only), env-var keys, or assume-role/STS — selected by config. |

---

## 3. Personas & Key User Journeys

**Persona — FinOps Engineer / Eng Lead / Founder (you).** Wants fast, trustworthy
answers and prioritized actions, without clicking through 12 console screens.

### Journey A — "What's my bill and where's it going?" (dashboard)
1. Open dashboard → KPI row: MTD spend, forecast EOM, Δ vs last month, anomalies count.
2. **Cost-by-service** table (ranked, with sparkline + Δ%).
3. **Double-click EC2** → drills into EC2 by *usage type* → click `BoxUsage:m5.xlarge`
   → by *region* → by *linked account* → (if CUR enabled) by *resource id / tag*.
4. Side chat panel: "Why did EC2 jump 40% last week?" → agent correlates anomaly +
   usage-type delta + a launched-instances narrative.

### Journey B — "How do I cut cost?" (chat or dashboard "Optimize" tab)
1. Ask "Find me savings." → Optimization specialist aggregates rightsizing + idle +
   Savings Plans/RI + Compute Optimizer + Trusted Advisor.
2. Returns a ranked table: *finding · monthly savings · effort · risk · evidence*.
3. In `artifacts` mode each row has **"Generate fix"** → Terraform/CLI snippet.
4. In `guarded_write` mode, allowlisted rows have **"Apply"** → confirmation modal → executes.

### Journey C — "Email me a weekly digest" (scheduled Workflow)
- A Workflow DAG runs on schedule, produces a markdown/HTML/JSON report
  (spend, top movers, anomalies, top 5 savings) and delivers to file/email/Slack/SNS.

---

## 4. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            Interfaces                                       │
│   Streamlit dashboard  ──┐                       ┌── FastAPI REST           │
│   (tables, charts,       │                       │   /query /drilldown      │
│    click-drilldown,      │                       │   /optimize /report ...  │
│    chat panel)           ▼                       ▼                          │
└───────────────────┬───────────────────────────────────┬────────────────────┘
                    │             Agent Core             │
                    ▼                                     ▼
        ┌───────────────────────────┐        ┌───────────────────────────┐
        │  Direct Tool Layer        │        │  FinOps Orchestrator Agent │
        │  (deterministic boto3     │        │  (Strands; Agents-as-Tools)│
        │   wrappers — fast path    │◀──────▶│  delegates to specialists  │
        │   for UI clicks)          │  same  │                            │
        └─────────────┬─────────────┘ tools  └─────────────┬──────────────┘
                      │                                     │
                      │              ┌──────────────────────┼──────────────────────┐
                      │              ▼            ▼          ▼            ▼          │
                      │      Cost-Analysis   Optimization  Anomaly/    CUR/Athena   │  Specialist
                      │      sub-agent       sub-agent     Forecast    sub-agent    │  sub-agents
                      │                                    sub-agent                │  (each = @tool)
                      │              └──────────────────────┬──────────────────────┘
                      ▼                                     ▼
        ┌──────────────────────────────────────────────────────────────────┐
        │                AWS Access Layer (boto3 sessions)                   │
        │   profile / env / assume-role · org account resolver · paginators │
        │   ret/throttle handling · response cache (TTL) · cost guardrails   │
        └──────────────────────────────────────────────────────────────────┘
                      │
                      ▼
   AWS APIs: ce · cost-optimization-hub · compute-optimizer · budgets ·
             support/trustedadvisor · bcm-data-exports · athena · organizations ·
             pricing · freetier · sts · savingsplans

   Bedrock Runtime (Claude Sonnet 4.x / Nova Pro / Haiku) for agent reasoning.
```

**Key architectural principle — one source of truth, two callers.**
Every AWS capability is a deterministic Python function in the **Direct Tool Layer**.
The same functions are registered as Strands `@tool`s on the agents. So:
- **UI clicks** (cost table, drill-down) call the tool layer **directly** — no LLM in
  the loop → fast, cheap, deterministic, exact numbers.
- **Chat / open-ended questions** go through the **agent**, which calls the same tools
  and adds reasoning/narrative.

This keeps numbers consistent between "click" and "ask," and bounds LLM token cost.

---

## 5. Multi-Agent Design (Strands patterns)

Following the [Strands multi-agent patterns](https://strandsagents.com/docs/user-guide/concepts/multi-agent/multi-agent-patterns/),
we use a **Hybrid**:

### 5.1 Interactive path — Agents as Tools (hierarchical)
A single **FinOps Orchestrator** agent holds the conversation, decides intent, and
delegates by calling specialist sub-agents that are wrapped as tools. Each specialist
has a focused system prompt + a narrow tool subset → smaller context, better accuracy,
controllable cost.

| Sub-agent | Responsibility | Primary tools |
|---|---|---|
| **Cost-Analysis** | Spend totals, cost-per-service, drill-down, trends, per-account split, forecast | `get_cost_summary`, `get_cost_by_service`, `drill_down`, `get_cost_by_account`, `get_cost_trend`, `get_cost_forecast`, `list_dimension_values` |
| **Optimization** | Savings findings, ranked & deduped across sources | `get_rightsizing_recommendations`, `get_compute_optimizer_recommendations`, `get_savings_plans_recommendations`, `get_reservation_recommendations`, `get_cost_optimization_hub_recommendations`, `get_trusted_advisor_cost_checks` |
| **Anomaly & Forecast** | Anomalies, budget status, forecast vs budget | `get_cost_anomalies`, `get_anomaly_monitors`, `get_budgets_status`, `get_cost_forecast` |
| **CUR / Athena** | Deep resource/tag-level queries, NL→SQL over CUR | `run_cur_query`, `describe_cur_schema`, `provision_cur_export` |
| **Account / Org** | Resolve account names, multi-account fan-out | `list_accounts`, `assume_account_role`, `get_caller_identity` |
| **Remediation** *(mode-gated)* | Generate fix artifacts / apply guarded actions | `generate_remediation_artifact`, `apply_guarded_action` |

> *Representative Strands shape — a specialist exposed as a tool:*
> ```python
> from strands import Agent, tool
> from strands.models import BedrockModel
>
> @tool
> def optimization_specialist(question: str) -> str:
>     """Find and rank AWS cost-savings opportunities (rightsizing, SP/RI, idle, TA).
>     Use for any 'how do I reduce cost / find savings' question."""
>     agent = Agent(
>         model=model_router.for_role("optimization"),
>         system_prompt=OPTIMIZATION_PROMPT,
>         tools=[get_rightsizing_recommendations, get_compute_optimizer_recommendations,
>                get_savings_plans_recommendations, get_reservation_recommendations,
>                get_cost_optimization_hub_recommendations, get_trusted_advisor_cost_checks],
>     )
>     return str(agent(question))
>
> orchestrator = Agent(
>     model=model_router.for_role("orchestrator"),
>     system_prompt=ORCHESTRATOR_PROMPT,
>     tools=[cost_analysis_specialist, optimization_specialist,
>            anomaly_forecast_specialist, cur_athena_specialist, account_org_specialist],
> )
> ```
> (Exact class/param names per the installed Strands version; treated as the integration contract, not copied verbatim.)

### 5.2 Scheduled path — Workflow (DAG)
A Strands **Workflow** encapsulates the repeatable digest as one reusable tool. Tasks
with no interdependency run in parallel; outputs feed dependents.

```
extract_context ─┬─▶ cost_by_service ───┐
                 ├─▶ cost_by_account ────┤
                 ├─▶ detect_anomalies ───┼─▶ synthesize_report ─▶ deliver
                 ├─▶ optimization_scan ──┤      (LLM narrative)    (file/email/
                 └─▶ forecast_vs_budget ─┘                          Slack/SNS)
```

### 5.3 Why not pure Graph/Swarm
- **Graph** (deterministic routing) is great for fixed flows but rigid for open-ended
  drill-down chat. We borrow its determinism only in the Workflow DAG.
- **Swarm** (emergent handoff) is powerful but harder to cost-bound and reason about for
  a numbers-must-be-exact use case. Avoided for v1; revisit for "investigation" mode.

---

## 6. Model Strategy (Bedrock with fallback)

A **ModelRouter** resolves a model per role from config/env, with graceful fallback.

| Role | Default | Rationale | Override env |
|---|---|---|---|
| Orchestrator | Claude Sonnet 4.x | Best multi-step routing & synthesis | `FINOPS_MODEL_ORCHESTRATOR` |
| Cost-Analysis | Claude Sonnet 4.x | Accurate number handling/narrative | `FINOPS_MODEL_COST` |
| Optimization | Claude Sonnet 4.x | Trade-off reasoning | `FINOPS_MODEL_OPT` |
| CUR NL→SQL | Claude Sonnet 4.x | Correct SQL gen | `FINOPS_MODEL_SQL` |
| Digest narrative | Nova Pro *or* Haiku | Cheaper bulk summarization | `FINOPS_MODEL_DIGEST` |

- Configured via **Bedrock inference-profile IDs** (region-specific, e.g.
  `us.anthropic.claude-sonnet-4-*`, `us.amazon.nova-pro-v1:0`,
  `us.anthropic.claude-haiku-*`). Exact IDs live in `config/models.yaml`, not hardcoded.
- **Prerequisite:** Bedrock **model access** must be enabled for the chosen models in the
  configured region; startup does a preflight check and prints a clear remediation message.
- **Fallback chain:** primary → secondary (e.g. Sonnet → Haiku) on
  `AccessDeniedException`/`ThrottlingException`, with backoff.
- **Optional Anthropic-API mode:** if `FINOPS_LLM_PROVIDER=anthropic`, use `ANTHROPIC_API_KEY`
  via Strands' Anthropic model provider (no Bedrock dependency).
- **Cost guardrails:** prompt-cache where supported; max-token caps; per-session token
  budget surfaced in observability.

---

## 7. Tool Catalog (the contract)

All tools are thin, typed, paginated boto3 wrappers returning **normalized dataclasses**
(JSON-serializable). Each is decorated `@tool` for the agent and callable directly by the UI.
`account` and `region` are optional params on read tools (default = caller's account).

### 7.1 Cost analysis & drill-down
| Tool | AWS API | Notes |
|---|---|---|
| `get_caller_identity()` | `sts:GetCallerIdentity` | Who am I / which account |
| `get_cost_summary(start, end, granularity, metric)` | `ce:GetCostAndUsage` | Totals; `metric` ∈ UnblendedCost/AmortizedCost/NetAmortizedCost |
| `get_cost_by_service(start, end, top_n, granularity)` | `ce:GetCostAndUsage` GroupBy=SERVICE | Ranked cost-per-service (dashboard table) |
| `get_cost_by_account(start, end, top_n)` | `ce:GetCostAndUsage` GroupBy=LINKED_ACCOUNT | Org/consolidated breakdown |
| **`drill_down(dimension_path, filters, start, end)`** | `ce:GetCostAndUsage` (+`...WithResources` if CUR) | **The "double-click"**: progressive group-by SERVICE→USAGE_TYPE→OPERATION→REGION→LINKED_ACCOUNT→(RESOURCE_ID via CUR) |
| `get_cost_trend(months, group_by)` | `ce:GetCostAndUsage` MONTHLY | Trend + Δ for sparklines/movers |
| `get_cost_forecast(start, end, metric, granularity)` | `ce:GetCostForecast` | EOM/EOQ forecast w/ confidence band |
| `list_dimension_values(dimension, start, end)` | `ce:GetDimensionValues` | Valid filter values |
| `get_cost_by_tag(tag_key, start, end)` | `ce:GetCostAndUsage` GroupBy=TAG | Showback/chargeback by cost-allocation tag |
| `list_cost_categories()` / `list_cost_allocation_tags()` | `ce`, `ce:ListCostAllocationTags` | Available slicers |

### 7.2 Optimization
| Tool | AWS API |
|---|---|
| `get_rightsizing_recommendations(service)` | `ce:GetRightsizingRecommendation` |
| `get_compute_optimizer_recommendations(resource_type)` | `compute-optimizer:Get*Recommendations` (EC2/ASG/EBS/Lambda/ECS/RDS) |
| `get_savings_plans_recommendations(term, payment, lookback)` | `ce:GetSavingsPlansPurchaseRecommendation` |
| `get_reservation_recommendations(service, term, payment)` | `ce:GetReservationPurchaseRecommendation` |
| `get_reservation_coverage_utilization()` | `ce:GetReservationCoverage` / `...Utilization` |
| `get_savings_plans_coverage_utilization()` | `ce:GetSavingsPlansCoverage` / `...Utilization` |
| `get_cost_optimization_hub_recommendations(filters)` | `cost-optimization-hub:ListRecommendations` (unified, dedup) |
| `get_trusted_advisor_cost_checks()` | `support:DescribeTrustedAdvisorCheck*` / `trustedadvisor` (needs Business/Enterprise support; degrades if not) |
| `get_idle_resources()` | derived: Compute Optimizer "Idle" + CUR zero-usage heuristics |

### 7.3 Anomaly, budget, forecast
| Tool | AWS API |
|---|---|
| `get_cost_anomalies(start, end, monitor_arn)` | `ce:GetAnomalies` |
| `get_anomaly_monitors()` / `get_anomaly_subscriptions()` | `ce:GetAnomalyMonitors` / `...Subscriptions` |
| `get_budgets_status()` | `budgets:DescribeBudgets` |
| `get_free_tier_usage()` | `freetier:GetFreeTierUsage` |

### 7.4 CUR / Athena (deep resource-level)
| Tool | AWS API |
|---|---|
| `describe_cur_schema()` | `glue`/Athena metadata for the CUR table |
| `run_cur_query(sql, max_scanned_gb)` | `athena:StartQueryExecution`+`GetQueryResults`; **scan-bytes cap** to bound Athena cost; SELECT-only allowlist |
| `nl_to_cur_query(question)` | LLM NL→SQL constrained to CUR schema; returns SQL for review before run |
| `provision_cur_export()` *(guarded write)* | `bcm-data-exports:CreateExport` + S3 bucket + Athena workgroup/db (one-time) |

### 7.5 Pricing & org
| Tool | AWS API |
|---|---|
| `get_unit_pricing(service, attributes)` | `pricing:GetProducts` |
| `list_accounts()` | `organizations:ListAccounts` (name↔id map; cached) |
| `assume_account_role(account_id)` | `sts:AssumeRole` into `FinOpsReadOnly` |

### 7.6 Remediation (mode-gated; see §9)
| Tool | Behavior |
|---|---|
| `generate_remediation_artifact(finding_id, format)` | Emits Terraform/CloudFormation/CLI for a finding. **No execution.** (`artifacts` + `guarded_write` modes) |
| `apply_guarded_action(action_id, confirmation_token)` | Executes an **allowlisted** action after human confirmation. (`guarded_write` only) |

**Guarded-write allowlist (v1):** `create_or_update_budget`, `create_anomaly_monitor`,
`delete_unattached_ebs_volume`, `release_unassociated_eip`, `delete_old_ebs_snapshot`,
`stop_idle_dev_instance` (tag-scoped), `enable_compute_optimizer`,
`enable_cost_optimization_hub`. Each requires: dry-run preview → human confirm → execute →
audit-log entry. No IAM/networking/data-deletion actions in v1.

---

## 8. AWS Access Layer

- **Session resolution** (in priority order, configurable):
  1. `assume_role` (config: base creds → `FinOpsReadOnly` role ARN) — preferred for org/multi-account.
  2. **Named profile** (`AWS_PROFILE` / config) from mounted `~/.aws`.
  3. **Env-var keys** (`AWS_ACCESS_KEY_ID` / `_SECRET_ACCESS_KEY` / `_SESSION_TOKEN`).
- **Region:** Cost Explorer/Budgets are global but **must be called via `us-east-1`**;
  Compute Optimizer/Athena use the configured operational region. Router handles per-service
  endpoint region automatically. (Your env currently has no region set → config requires
  `AWS_REGION`, defaulting operational region to `us-east-1` unless overridden.)
- **Org mode:** run from payer account; `list_accounts` builds id→name map; cost grouped by
  `LINKED_ACCOUNT`; optional per-account deep dives via `assume_account_role`.
- **Reliability:** adaptive retries, throttle backoff, pagination helpers, partial-result
  flags. **Response cache** (TTL, default 1h, configurable) keyed by (account, api, params)
  to cut repeat Cost Explorer calls (which are billed per request).
- **Cost guardrails on the agent itself:** Cost Explorer API calls are **$0.01 each** and
  Athena scans are billed per TB — the layer tracks/【caps】 these and surfaces a
  "this query will cost ~$X" estimate for expensive Athena runs.

---

## 9. Action Posture Modes

Selected by `FINOPS_MODE` (env/config) and switchable in the dashboard sidebar. Mode
controls **which tools are registered** and **which IAM policy** is expected.

| Mode | Tools loaded | IAM | UX |
|---|---|---|---|
| `advisory` *(default)* | Read tools only | Read-only policy | Analysis + recommendations only |
| `artifacts` | Read + `generate_remediation_artifact` | Read-only policy | Adds "Generate fix" → script/IaC (never executed) |
| `guarded_write` | Read + artifacts + `apply_guarded_action` | Read-only **+ scoped write allowlist** | Adds "Apply" → dry-run → **human confirm** → execute → audit log |

- Confirmation is enforced server-side: `apply_guarded_action` rejects calls without a
  fresh, single-use `confirmation_token` minted by an explicit human approval step.
- Every write is recorded to an **audit log** (who/what/when/before/after/result).
- The LLM can *propose* but **cannot self-approve** a write.

---

## 10. Interfaces

### 10.1 Streamlit dashboard
- **Overview:** KPI row (MTD, forecast EOM, Δ MoM, open anomalies, potential savings $).
- **Cost Explorer tab:** ranked **cost-per-service** table (sparkline + Δ%), period &
  granularity controls, account selector (org), tag/cost-category slicers.
- **Double-click drill-down:** clicking a row pushes onto a **breadcrumb drill stack**
  (`Service ▸ UsageType ▸ Operation ▸ Region ▸ Account ▸ Resource`) and calls
  `drill_down(...)` directly (fast path). Back/breadcrumb navigation supported.
- **Optimization tab:** ranked findings (savings $, effort, risk, source, evidence);
  per-row "Generate fix" / "Apply" by mode.
- **Anomalies/Budgets tab:** anomaly timeline, budget gauges, forecast-vs-budget.
- **Chat panel (always visible):** free-form questions → orchestrator agent; streams
  reasoning + renders any returned tables/charts. Drill context is shared with chat
  ("explain this spike").

### 10.2 FastAPI REST
| Endpoint | Purpose |
|---|---|
| `POST /query` | NL question → orchestrator agent (optionally streamed via SSE) |
| `GET /cost/summary`, `/cost/by-service`, `/cost/by-account` | Deterministic tool-layer responses |
| `POST /cost/drilldown` | `{dimension_path, filters, period}` → drill data |
| `GET /optimize/recommendations` | Aggregated, ranked savings |
| `GET /anomalies`, `/budgets`, `/forecast` | Direct tool data |
| `POST /report/digest` | Run the Workflow DAG, return report (json/markdown/html) |
| `POST /actions/preview` / `POST /actions/apply` | Guarded-write dry-run / execute (mode-gated) |
| `GET /healthz`, `/config` | Liveness; effective (redacted) config & mode |

- OpenAPI auto-docs at `/docs`. Optional bearer-token auth for non-local exposure.
- Streamlit consumes the same tool layer in-process (no network hop) for low latency; the
  REST API is for external integration.

---

## 11. Scheduled Digest (Workflow)

- Triggered by: local `cron`/`schedule` loop, container entrypoint flag
  (`--mode digest`), or EventBridge (if later deployed). Not required for interactive use.
- Output formats: Markdown, HTML, JSON. Delivery adapters: local file, **SES email**, **Slack
  webhook**, **SNS** (all optional/configured).
- Content: spend & trend, top movers (Δ services/accounts), open anomalies, budget status,
  top-5 ranked savings with estimated $.

---

## 12. Docker & Sandbox

### 12.1 Images & compose
- **Multi-stage Dockerfile**, Python 3.12-slim base, non-root `finops` user, no build
  toolchain in final layer.
- **`docker-compose.yml`** with services:
  - `dashboard` (Streamlit, port 8501)
  - `api` (FastAPI/uvicorn, port 8000)
  - shared volume for config; both import the same `finops_core` package.
- **Credentials** wired three ways (pick via env):
  - `~/.aws` bind-mounted **read-only** (`/home/finops/.aws:ro`) + `AWS_PROFILE`.
  - `AWS_ACCESS_KEY_ID/...` via `.env` / docker secrets.
  - Assume-role: base creds (either of above) + `FINOPS_ROLE_ARN`.

### 12.2 Hardened "sandbox" compose profile (`docker-compose.sandbox.yml`)
For running in a restricted/sandboxed context:
- `read_only: true` root filesystem + explicit `tmpfs` for scratch.
- `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, non-root uid.
- **Egress allowlist** to AWS endpoints + Bedrock only (documented; enforced via the
  sandbox's network policy / proxy). No inbound except the mapped UI/API ports on localhost.
- Credentials mounted **read-only**; no write to `~/.aws`.
- Resource limits (cpu/mem) set; secrets never baked into the image or logs.

### 12.3 Local (no Docker)
- `pip install -e .` + `make dashboard` / `make api`; uses the same config + `~/.aws`.

---

## 13. IAM Permissions

### 13.1 Read-only (`advisory` / `artifacts`) — managed-policy baseline + explicit allows
- AWS managed **`Billing` (read)**, **`AWSBilling ReadOnlyAccess`**-style, plus explicit:
  `ce:Get*`, `ce:List*`, `ce:Describe*`, `cost-optimization-hub:ListRecommendations`/`Get*`/`ListEnrollmentStatuses`,
  `compute-optimizer:Get*`/`DescribeRecommendationExportJobs`, `budgets:View*`/`Describe*`,
  `freetier:GetFreeTierUsage`, `pricing:GetProducts`/`DescribeServices`,
  `organizations:ListAccounts`/`DescribeOrganization`, `sts:GetCallerIdentity`,
  `support:DescribeTrustedAdvisor*` (or `trustedadvisor:*` read), `cur:DescribeReportDefinitions`/`bcm-data-exports:Get*`/`List*`,
  `athena:StartQueryExecution`/`GetQueryExecution`/`GetQueryResults`/`StopQueryExecution`,
  `glue:GetTable`/`GetDatabase`/`GetPartitions`, `s3:GetObject`/`ListBucket` (CUR + Athena output only),
  `bedrock:InvokeModel`/`InvokeModelWithResponseStream` (chosen model ARNs).
- Provided as a ready-to-apply JSON policy (`iam/finops-readonly-policy.json`).

### 13.2 Org/assume-role
- `FinOpsReadOnly` role per linked account trusting the payer/runner principal; base
  principal gets `sts:AssumeRole` on those role ARNs.

### 13.3 Guarded-write add-on (`guarded_write` only)
- Separate, **narrowly scoped** policy for the allowlist only (e.g. `budgets:Create/Modify`,
  `ce:CreateAnomalyMonitor`, `ec2:DeleteVolume`/`ReleaseAddress`/`DeleteSnapshot`/`StopInstances`
  **with tag/condition constraints**, `compute-optimizer:UpdateEnrollmentStatus`,
  `cost-optimization-hub:UpdateEnrollmentStatus`, `bcm-data-exports:CreateExport`,
  `s3:CreateBucket`/`PutBucketPolicy` for CUR provisioning). Disabled by default.
- Principle: **least privilege; resource/tag-scoped; no IAM/network/data-plane deletes.**

---

## 14. Security & Guardrails

- **Default read-only.** Writes require explicit mode + per-action human confirmation.
- **Secrets hygiene:** never log credentials; redact account IDs in logs by default
  (configurable); no creds in image; `.env`/secrets git-ignored.
- **Athena/CE cost safety:** SELECT-only SQL allowlist, scanned-bytes cap, CE request
  counter, expensive-query confirmation.
- **NL→SQL safety:** generated SQL is schema-constrained, shown for review, parameter-safe,
  and rejected if it isn't a single read query.
- **Audit log** for every write action.
- **Prompt-injection posture:** AWS data is treated as data, not instructions; tools return
  structured results, not free-form commands; the orchestrator cannot execute shell.

---

## 15. Observability & Evaluation

- Strands tracing/observability + structured logs: per-request tool calls, latency, token
  usage, **estimated LLM $ and AWS-API $** per session.
- OpenTelemetry export optional (console/OTLP).
- **Numerical accuracy harness:** golden tests assert agent/tool numbers match a direct
  Cost Explorer/CUR query within tolerance (numbers must be exact, not "LLM-estimated").
- Eval set of canonical questions ("top 5 services last month", "EC2 by usage type",
  "biggest savings") with expected tool-call shapes.

---

## 16. Configuration

`config/finops.yaml` (+ env overrides; env wins). Redacted view at `GET /config`.
```yaml
llm:
  provider: bedrock            # bedrock | anthropic
  region: us-east-1
  roles:                       # inference-profile IDs per role
    orchestrator: us.anthropic.claude-sonnet-4-...
    digest:       us.amazon.nova-pro-v1:0
  fallback: [claude-sonnet, claude-haiku]
aws:
  auth: profile                # profile | env | assume_role
  profile: default
  region: us-east-1            # operational region
  ce_region: us-east-1         # Cost Explorer endpoint
  org_mode: false
  assume_role_arns: []         # for org/multi-account
mode: advisory                 # advisory | artifacts | guarded_write
cur:
  enabled: false               # auto-detected; provision via tool
  database: null
  table: null
  workgroup: null
  output_s3: null
cache:
  ttl_seconds: 3600
report:
  delivery: [file]             # file | ses | slack | sns
guardrails:
  athena_max_scanned_gb: 10
  require_confirmation: true
```

---

## 17. Proposed Project Structure
```
AWSFinOpsAgent/
├── SPEC.md
├── pyproject.toml
├── Makefile
├── Dockerfile
├── docker-compose.yml
├── docker-compose.sandbox.yml
├── .env.example
├── config/
│   ├── finops.yaml
│   └── models.yaml
├── iam/
│   ├── finops-readonly-policy.json
│   └── finops-guarded-write-policy.json
├── finops_core/
│   ├── aws/            # session resolver, org resolver, cache, paginators
│   ├── tools/          # @tool wrappers (cost, optimize, anomaly, cur, pricing, org, remediation)
│   ├── agents/         # orchestrator + specialists + prompts
│   ├── workflow/       # scheduled digest DAG + delivery adapters
│   ├── models/         # ModelRouter, fallback
│   ├── schemas/        # normalized dataclasses
│   └── config.py
├── apps/
│   ├── dashboard/      # Streamlit
│   └── api/            # FastAPI
└── tests/
    ├── unit/           # tool wrappers (moto/botocore stubs)
    ├── accuracy/       # numbers-match-CE golden tests
    └── e2e/            # docker smoke
```

---

## 18. Milestones

| Phase | Deliverable | Exit criteria |
|---|---|---|
| **0. Scaffold** | Repo, config, AWS session layer, model router, Bedrock preflight | `get_caller_identity` works in Docker w/ all 3 cred modes |
| **1. Cost core** | Cost-analysis tools + Cost-Analysis agent + CLI smoke | Accurate cost-per-service + drill-down vs console |
| **2. Dashboard MVP** | Streamlit overview + cost table + **double-click drill-down** + chat | Journey A end-to-end |
| **3. Optimization** | Optimization tools/agent, ranked dedup findings | Journey B (advisory) |
| **4. Anomaly/forecast/budgets** | Tools + tab | Anomalies & budgets visible |
| **5. API** | FastAPI over same core | All endpoints + OpenAPI |
| **6. CUR/Athena** | NL→SQL, query, **provision** tool | Resource-level drill-down when CUR on |
| **7. Workflow digest** | Scheduled report + delivery | Markdown/HTML/JSON digest |
| **8. Remediation modes** | `artifacts` + `guarded_write` + audit | Confirmed action w/ audit entry |
| **9. Org/multi-account** | assume-role fan-out, per-account split | Per-linked-account costs |
| **10. Hardening** | Sandbox compose, IAM policies, accuracy harness, observability | Sandbox run + green accuracy tests |

---

## 19. Assumptions & Open Questions

**Assumptions**
- `~/.aws` `[default]` profile (detected) is the starting identity; region defaults to
  `us-east-1` (none set in env) until configured.
- Cost Explorer is enabled on the account (one-time, may take ~24h on first enable).
- Trusted Advisor cost checks require Business/Enterprise Support; degrade gracefully.
- Bedrock model access will be enabled in the chosen region before first run.

**Open questions (for later, non-blocking)**
1. Digest delivery target(s) — email (SES verified identity?), Slack, or file only for v1?
2. For org mode, is the local `default` profile the **payer/management** account?
3. Any existing cost-allocation tags / cost categories to prioritize for showback?
4. Preferred Athena scan cost ceiling (default 10 GB/query)?
5. Should chat history persist across sessions (memory store), or be ephemeral per session?

---

## 20. Acceptance Criteria (v1 "done")
- From a clean checkout, `docker compose up` brings up dashboard + API using local AWS creds.
- Dashboard shows accurate **cost-per-service** and supports **double-click drill-down**
  to at least usage-type/operation/region/account (resource-level when CUR enabled).
- Chat answers "where is my money going" and "how do I reduce my bill" with numbers that
  **match Cost Explorer** and a ranked, evidenced savings list.
- Mode switch among `advisory` / `artifacts` / `guarded_write` changes available actions;
  a guarded write requires explicit confirmation and is audit-logged.
- Runs in the hardened **sandbox** compose profile (read-only FS, non-root, dropped caps).
