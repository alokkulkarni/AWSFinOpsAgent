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
| **Distribution** | **Fully distributed, Docker-based**: each sub-agent runs as a Strands **A2A server** container; each tool domain runs as a **FastMCP (MCP Streamable-HTTP) server** container; the orchestrator calls sub-agents via the **A2A client**. One shared `finops_core` library is reused inside every service image. |
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

**Distributed, Docker-based topology.** Every tier is its own container on a shared
network. Agents talk to each other over **A2A** (HTTP/JSON-RPC + agent cards); agents
reach tools over **MCP** (Streamable HTTP). One `finops_core` library is reused inside
every image (the deterministic engine + Strands wrappers + servers).

```
   Streamlit dashboard ─┐                 ┌─ FastAPI REST gateway      (interface tier)
   (click-drilldown,    │                 │  /query /drilldown ...
    chat panel)         └──────┬──────────┘
                               │  A2A / HTTP
                               ▼
                   ┌────────────────────────────┐
                   │  Orchestrator  (A2A server) │  container :9000   ── orchestrator tier
                   │  Strands Agent + A2A client │
                   └─────────────┬──────────────┘
                                 │  A2A (agent cards, JSON-RPC)
        ┌────────────────┬───────┴────────┬──────────────────┐
        ▼                ▼                ▼                  ▼
 ┌────────────┐  ┌────────────┐   ┌────────────┐    ┌────────────┐
 │Cost-Analysis│ │Optimization│   │ Anomaly/   │    │ CUR/Athena │   sub-agent tier
 │ A2A :9001   │ │ A2A :9002  │   │ Forecast   │    │ A2A :9004  │   (each = A2AServer
 └─────┬───────┘ └─────┬──────┘   │ A2A :9003  │    └─────┬──────┘    container)
       │  MCP          │  MCP     └─────┬──────┘          │  MCP
       ▼               ▼                ▼                 ▼
 ┌────────────┐  ┌────────────┐  ┌────────────┐   ┌────────────┐
 │ cost-tools │  │ optimize-  │  │ anomaly-   │   │ cur-tools  │     tool tier
 │ MCP :8081  │  │ tools MCP  │  │ tools MCP  │   │ MCP :8084  │     (each = FastMCP
 └─────┬──────┘  └─────┬──────┘  └─────┬──────┘   └─────┬──────┘      container)
       └───────────────┴───────────────┴────────────────┘
                                 │  boto3 (per-service AWS Access Layer in finops_core)
                                 ▼
   AWS APIs: ce · cost-optimization-hub · compute-optimizer · budgets ·
             support/trustedadvisor · bcm-data-exports · athena · organizations ·
             pricing · freetier · sts          +  Bedrock Runtime (agent reasoning)
```
*(Phase 1 ships the cost slice — orchestrator + cost-agent + cost-tools — live and verified.
Optimization/Anomaly/CUR tiers are dashed-in templates for later phases.)*

**Key architectural principle — one source of truth.**
Every AWS capability is a deterministic Python function in `finops_core` (e.g.
`CostExplorer`). Each is served as an **MCP tool** (for agents) and is also callable
**directly** by the API/UI fast path (no LLM → exact, cheap numbers for table clicks).
So "click" and "ask" resolve to the *same* function and always agree; the LLM adds
narrative, never arithmetic. Distribution wraps — never forks — this core.

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

### 5.4 Agent Skills (progressive disclosure)  ✅ *Phase 11 — opt-in, off by default.*

Specialist *procedures* that are needed only **sometimes** (a Savings-Plan-vs-RI decision, a
drill-down method, an anomaly-triage runbook) live as **skills** rather than bloating the
always-on system prompt. Built on the Strands [`AgentSkills`](https://strandsagents.com/docs/user-guide/concepts/plugins/skills/)
plugin: only each skill's `name` + `description` are front-loaded into the prompt; the full
`SKILL.md` is pulled on demand when the model invokes the auto-registered `skills` tool.

**A skill is a directory** (Agent Skills spec — `name` must equal the directory name):
```
finops_core/skills/<agent>/<skill-name>/
  ├── SKILL.md            # YAML frontmatter (name, description, allowed-tools) + instructions
  └── references/         # optional deep-dive files, pulled via the scoped reader
```
Per-agent folders (`finops_core/skills/{cost,optimize,anomaly}/`, `devops_core/skills/estate/`)
keep each agent's reach minimal. The reusable machinery lives in `finops_core/skills/__init__.py`
(discovery, gating, `attach_skills`, the scoped reader); `devops_core/skills` reuses it — mirroring
how steering and the `ModelRouter` are shared.

**Wiring.** Each `build_*_agent` factory accepts `skills: Optional[bool]` (None → `cfg.skills_enabled`).
When on, `attach_skills` adds `plugins=[AgentSkills(...)]` and appends a **skills-dir-scoped file
reader** to the tool list. When off (the default) it is a byte-for-byte no-op — no plugin, no extra
tool — so existing behavior is unchanged. Enable via `skills.enabled` (`config/finops.yaml`),
`FINOPS_SKILLS=1`, the `--skills/--no-skills` flag on `finops ask` / `devops ask`, the dashboard
sidebar **"Agent skills (beta)"** toggle (FinOps + DevOps), or `build_*_agent(skills=True)`.
Authoring guide: `docs/SKILLS.md`.

**Posture (consistent with §14).**
- Skills are **instructions, never data** — exact figures still come from the tool layer
  (numbers-must-be-exact). Each seed skill explicitly restates "read every number from a tool".
- The reader is the **only** filesystem reach skills add, and it is **least-privilege**: paths
  resolving outside the agent's own skills folder are rejected (so the cost agent cannot read the
  optimize agent's files). `SKILL.md` `allowed-tools` documents intent; the agent is only ever
  granted that scoped reader.

**Skills vs. the other mechanisms** — system prompt = always-on rules; **steering** = the agent's
core playbook; **tools** = deterministic AWS execution; **skills** = sometimes-needed procedures
within one agent; **sub-agents** = different roles. Seeds shipped: `cost-drilldown-playbook`,
`savings-plan-vs-ri`, `anomaly-triage`, `incident-triage-runbook`.

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

### 7.2 Optimization  ✅ *Phase 3 — built as the distributed optimize tier (optimize-tools MCP + optimize-agent A2A); each source degrades to a note when unavailable/not-enrolled.*
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

### 7.3 Anomaly, budget, forecast  ✅ *Phase 4 — distributed anomaly tier (anomaly-tools MCP + anomaly-agent A2A): anomalies (ranked, root causes), budgets (actual + forecast vs limit, breach flags), forecast-vs-budget.*
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

### 7.5 Pricing & org  ✅ *Phase 9 — `finops_core/aws/org.py` OrgResolver: list_accounts (Organizations, paginated, cached), id→name map, assume_account (FinOpsReadOnly fan-out). Wired into cost-by-account (CLI/API/MCP) + `finops org accounts`. Graceful single-account fallback (IAM alias).*
| Tool | AWS API |
|---|---|
| `get_unit_pricing(service, attributes)` | `pricing:GetProducts` |
| `list_accounts()` | `organizations:ListAccounts` (name↔id map; cached) |
| `assume_account_role(account_id)` | `sts:AssumeRole` into `FinOpsReadOnly` |

### 7.6 Remediation (mode-gated; see §9)  ✅ *Phase 8 — `finops_core/remediation/`: artifacts.py (CLI/Terraform generators), actions.py (allowlist + preview/apply), audit.py (append-only log + single-use token store). Surfaces: `finops fix`, `finops action {list,preview,apply}`, `/fix`, `/actions/*`.*
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

## 9. Action Posture Modes  ✅ *Phase 8 — implemented & enforced in CLI + API.*

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

### 10.1 Streamlit dashboard  ✅ *Phase 2 — KPIs + cost-per-service + drill-down + trend + chat built & smoke-tested; Optimization/Anomaly tabs pending their phases.*
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

### 10.2 FastAPI REST  ✅ *Phase 5 — `apps/api/main.py`: /healthz, /config, /cost/{summary,by-service,by-account,drilldown,trend,forecast}, /optimize/recommendations, /anomalies, /budgets, POST /query (intent-routed). OpenAPI at /docs. Injectable deps (testable). `report/digest` + `actions/*` land in Phases 7/8.*
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

## 11. Scheduled Digest (Workflow)  ✅ *Phase 7 — `finops_core/workflow/`: `gather()` runs the independent sections in parallel (ThreadPoolExecutor = the DAG), renders md/html/json deterministically, optional `digest`-model narrative; `delivery.py` = file/Slack/SNS/SES. Surfaces: `finops digest`, `POST /report/digest`, one-shot `digest` compose service (cron/EventBridge).*

- Triggered by: local `cron`/`schedule` loop, container entrypoint flag
  (`--mode digest`), or EventBridge (if later deployed). Not required for interactive use.
- Output formats: Markdown, HTML, JSON. Delivery adapters: local file, **SES email**, **Slack
  webhook**, **SNS** (all optional/configured).
- Content: spend & trend, top movers (Δ services/accounts), open anomalies, budget status,
  top-5 ranked savings with estimated $.

---

## 12. Docker & Sandbox

### 12.1 Images & compose (distributed)
- **One image** (Python 3.12-slim base, non-root `finops` uid 10001) runs every service via
  the `finops serve <service>` entrypoint. Built with the `[agent,api]` extras (Strands
  A2A + MCP + FastAPI).
- **`docker-compose.yml`** services (each its own container, shared network, YAML-anchored base):
  - `cost-tools` — FastMCP server (`:8081/mcp`)  *(tool tier)*
  - `cost-agent` — Cost-Analysis A2A server (`:9001`), consumes `cost-tools` over MCP  *(sub-agent tier)*
  - `orchestrator` — A2A server (`:9000`, host-published), routes to sub-agents via A2A client
  - `preflight` — one-shot identity + Bedrock check
  - *(later phases add `optimize-tools`/`optimize-agent`, `anomaly-*`, `cur-*`, plus `api` + `dashboard`)*
- **Inter-service addressing** via Docker DNS + `FINOPS_*_URL` / `FINOPS_A2A_PUBLIC_URL` env
  (e.g. `http://cost-tools:8081/mcp`, `http://cost-agent:9001`). MCP connect retries on startup races.
- **Credentials** wired three ways (each container mounts `~/.aws:ro` or uses env / assume-role):
  agent + tool containers each need creds (Bedrock for agents, Cost Explorer for tools).

### 12.2 Hardened "sandbox" overlay (`docker-compose.sandbox.yml`)
Applied to **every** service: `read_only: true` root FS + `tmpfs` scratch, `cap_drop: [ALL]`,
`security_opt: [no-new-privileges:true]`, non-root uid, `pids_limit` + `mem_limit`. Egress is
AWS + Bedrock only (documented; enforced by the sandbox network policy). Creds read-only; no
secrets in images/logs. **Verified**: full stack runs and answers under the hardened overlay.

### 12.3 Local (no Docker)
- `make install` then `finops serve cost-tools` / `cost-agent` / `orchestrator` in separate
  shells, or `finops ask "..."` for the in-process agent. Same `finops_core` + `~/.aws`.

---

## 13. IAM Permissions

> ✅ **Delivered**: `iam/finops-readonly-policy.json` (advisory/artifacts) and
> `iam/finops-guarded-write-policy.json` (guarded_write only) are committed, plus
> `scripts/setup_finops_iam.sh` + `docs/IAM.md` to create a dedicated read-only `finops`
> profile and stop using root. Preflight warns on root credentials.

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
- **Steering & guardrails (delivered):** agent behavior lives in versioned steering files
  (`finops_core/steering/*.md`); a **ReadOnlyGuard** hook cancels write-shaped tools unless
  `guarded_write` (defense-in-depth at the tool layer); **structured output** (`FinOpsAnswer`)
  returns exact figures as typed fields; an optional **Bedrock Guardrail** (PII / prompt-attack,
  off by default) is wired via `ModelRouter` — see `docs/GUARDRAILS.md` (+ the PII-logging caveat).
- **Agent skills (opt-in, §5.4):** skills carry *instructions only* (numbers still come from
  tools); the lone filesystem capability they add is a **per-agent directory-scoped reader** that
  rejects path-escape, keeping the read-only/least-privilege posture intact.

---

## 15. Observability & Evaluation  ✅ *Phase 10 — `finops_core/observe.py` ApiMeter (botocore after-call hook → call counts + estimated Cost-Explorer spend, exposed at `GET /metrics`) + structured logging; `finops_core/accuracy.py` reconciles tool figures vs a raw GetCostAndUsage (`finops accuracy`, gated live pytest). Sandbox + IAM delivered in earlier phases.*

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
│   ├── aws/            # session resolver, identity+redaction, TTL cache  [✓]
│   ├── cost/           # CostExplorer engine + date helpers              [✓ Phase 1]
│   ├── schemas/        # normalized dataclasses (cost; later optimize…)  [✓]
│   ├── tools/          # Strands @tool wrappers (cost; later optimize…)  [✓ cost]
│   ├── mcp_servers/    # FastMCP tool servers (cost_server; later …)     [✓ cost]
│   ├── services/       # A2A servers: cost_agent, orchestrator (+helper) [✓ cost]
│   ├── agents/         # agent builders + prompts                        [✓ cost]
│   ├── steering/       # versioned .md playbooks (system prompts)        [✓]
│   ├── skills/         # agent skills: <agent>/<skill>/SKILL.md (opt-in) [✓ Phase 11]
│   ├── models/         # ModelRouter (Bedrock + fallback + preflight)    [✓]
│   ├── workflow/       # scheduled digest DAG + delivery adapters        [ ]
│   ├── format.py       # CLI table rendering                             [✓]
│   ├── preflight.py · cli.py · config.py                                 [✓]
├── apps/
│   ├── dashboard/      # Streamlit  [ Phase 2 ]
│   └── api/            # FastAPI    [ Phase 5 ]
└── tests/
    ├── unit/           # dates + Cost Explorer normalization (botocore Stubber)  [✓]
    └── accuracy/       # numbers-consistency invariant                           [✓]
```
*([✓] = built & verified in Phase 0/1.)*

---

## 18. Milestones

| Phase | Deliverable | Exit criteria | Status |
|---|---|---|---|
| **0. Scaffold** | Repo, config, AWS session layer, model router, Bedrock preflight | `get_caller_identity` works in Docker w/ all 3 cred modes | ✅ **Done** (preflight PASS local + Docker + sandbox) |
| **1. Cost core** | Cost-analysis tools + Cost-Analysis agent + CLI smoke | Accurate cost-per-service + drill-down vs console | ✅ **Done** — see Phase-1 evidence below |
| **1d. Distribute (cost slice)** | cost-tools MCP server + cost-agent A2A + orchestrator A2A + compose | Distributed stack answers in Docker + sandbox, numbers exact | ✅ **Done** (bundled into Phase 1) |
| **2. Dashboard MVP** | Streamlit overview + cost table + **double-click drill-down** + chat | Journey A end-to-end | ✅ **Done** — deterministic data layer; drill-down verified headlessly (AppTest) + dockerized |
| **3. Optimization** | Optimization tools/agent, ranked dedup findings | Journey B (advisory) | ✅ **Done** — distributed optimize tier (MCP + A2A); 2-agent orchestrator routing verified in Docker; graceful degradation when sources not enrolled |
| **4. Anomaly/forecast/budgets** | Tools + tab | Anomalies & budgets visible | ✅ **Done** — distributed anomaly tier (MCP + A2A); real anomalies + over-budget surfaced in CLI/dashboard; orchestrator routes anomaly Qs (budget-routing can occasionally deflect — see number-relay note) |
| **5. API** | FastAPI over same core | All endpoints + OpenAPI | ✅ **Done** — deterministic /cost /optimize /anomalies /budgets + intent-routed /query; OpenAPI /docs; dockerized; verified live |
| **6. CUR/Athena** | NL→SQL, query, **provision** tool | Resource-level drill-down when CUR on |
| **7. Workflow digest** | Scheduled report + delivery | Markdown/HTML/JSON digest | ✅ **Done** — parallel-DAG gather → md/html/json render (deterministic) + optional LLM narrative; file/Slack/SNS/SES delivery; `finops digest`, POST /report/digest, one-shot compose service |
| **8. Remediation modes** | `artifacts` + `guarded_write` + audit | Confirmed action w/ audit entry | ✅ **Done** — artifact generator + allowlisted guarded actions (preview→single-use token→apply→audit); mode-gated CLI (`fix`, `action`) + API (`/fix`, `/actions/*`); verified guard + bad-token rejection (no real mutation; apply path mock-tested) |
| **9. Org/multi-account** | assume-role fan-out, per-account split | Per-linked-account costs | ✅ **Done** — OrgResolver (list accounts, id→name, assume-role); cost-by-account name-enriched (CLI/API/cost-tier); verified live on a real Organizations payer (3 accounts: invincible/Audit/Log Archive) |
| **10. Hardening** | Sandbox compose, IAM policies, accuracy harness, observability | Sandbox run + green accuracy tests | ✅ **Done** — sandbox + IAM landed earlier; this phase adds the AWS-API meter (CE-spend estimate, /metrics), `finops accuracy` reconciliation (live PASS: Δ $2e-06), structured logging |
| **11. Agent skills** | `AgentSkills` plugin wired into all four agents (cost/optimize/anomaly/devsecops), per-agent skill folders, skills-dir-scoped reader, opt-in config + CLI flag + dashboard toggle | Default-off no-op; skills discovered + threaded when enabled; reader rejects path-escape | ✅ **Done** — `finops_core/skills` + `devops_core/skills`; 4 seed skills; enable via `skills.enabled`/`FINOPS_SKILLS`/`--skills`/sidebar toggle; `docs/SKILLS.md`; 29 unit tests (165 total green) |

### Phase-1 verification evidence (2026-06-19)
- **Numbers reconcile against live Cost Explorer**: `by-service` total == `summary` total
  ($298.14, last 3 mo); MTD ($172.60) == the June slice; **drill-down** VPC→usage-type totals
  $17.61 == its service line; all sub-breakdowns sum to the grand total.
- **In-process agent** (Claude Sonnet 4.5 on Bedrock) calls `get_cost_by_service` → `drill_down`
  and returns figures identical to the deterministic CLI.
- **Distributed** (3 containers, A2A + MCP): cost-agent and orchestrator return the same exact
  numbers — in normal Docker **and** the hardened sandbox overlay.
- **Tests**: 14 unit/accuracy tests pass (date presets, CE normalization via botocore Stubber,
  by-service==summary invariant).
- **Number-relay & routing** (was a known gap): resolved for the product path —
  (1) all user-facing numbers in the **dashboard/CLI come from the deterministic tool layer**,
  never an LLM; (2) every agent model runs at **temperature 0**; (3) a deterministic
  **`IntentRouter`** (`finops route`, dashboard chat) classifies cost/optimize/anomaly by rules
  and forwards to one specialist — **no orchestrator-LLM routing guesswork** (this fixed the
  budget-question deflection). The LLM-orchestrator A2A service remains for emergent multi-agent
  routing, but is no longer on the critical path.

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
