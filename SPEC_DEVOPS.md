# AWS DevOps / Estate Agent — Technical Specification

> **Status:** Draft v0.1 (spec-first)
> **Owner:** Alok Kulkarni
> **Built with:** Strands Agents SDK + Amazon Bedrock — reusing the FinOps agent's foundation.
> **Companion to:** `SPEC.md` (FinOps). This is the second product in the platform.
> **Date:** 2026-06-21

---

## 1. Purpose
A DevOps/estate agent that **scans the entire AWS estate** (root or Organization/enterprise),
**maps accounts → infra → deployed components**, **draws the estate** as a native `.drawio`
diagram (AWS icons/styles) plus a rendered **PNG/SVG**, and **answers questions** about
components, services, and topology. Same standards as FinOps (distributed A2A+MCP, Docker,
deterministic tools, TDD, PR-per-change, read-only by default).

The frontend lets the user pick which agent to use: **FinOps** or **DevOps**.

## 2. Locked decisions
| Decision | Choice |
|---|---|
| **Discovery** | **All sources, graceful**: AWS Config aggregator → Resource Explorer → Resource Groups Tagging API → per-service describes. Degrades like FinOps. |
| **Diagram** | Native **`.drawio`** (mxGraphModel) with **AWS shapes**, exported to **PNG/SVG** via the draw.io CLI (`-x -f <fmt> -e`); headless draw.io container in Docker; self-contained **SVG fallback** so the image always renders. Per the `drawio` skill. |
| **Scope** | **Comprehensive + network topology** (VPC/subnets/routing/peering/TGW/endpoints/SG + compute/data/edge/serverless). |
| **Accounts** | **Fan out to all Organization members** via assume-role (read-only role per account); single-account when no role. |
| **Foundation** | Reuse `finops_core`: AWS sessions, `OrgResolver`, `Config`, `ModelRouter` (Sonnet 4.6, temp 0, caching, maxTokens), hooks (`ReadOnlyGuard`), modes, observability. New code in **`devops_core`**. |

### Environment findings (probe, 2026-06-21)
- Config aggregator `AWSConfigurationAggregatorForObservabilityAdmin` exists but reports **0
  resources** → recording not enabled in sources; the engine falls through to Resource Explorer.
- **Resource Explorer is enabled** (per-region LOCAL indexes) and returns resources — the
  effective primary source.
- Tagging API works; **Organization = 3 accounts** (invincible / Audit / Log Archive).
- draw.io desktop CLI not installed locally (Node 26 is) → Docker headless render + SVG fallback.

## 3. Architecture (reuses the FinOps foundation)
```
   Frontend product selector:  [ FinOps ]  [ DevOps ]      (Streamlit + FastAPI)
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                                ▼
          DevOps orchestrator / IntentRouter                 estate views (deterministic)
                      │ A2A                                   scan · diagram · inventory
                      ▼
           devops-agent  (A2A sub-agent)
                      │ MCP
                      ▼
           devops-tools  (FastMCP server)  ── EstateScanner ─┐
                      │                       DiagramBuilder  │  reuse finops_core:
                      ▼                                       │  aws/session · aws/org
   AWS: config · resource-explorer-2 · resourcegroupstaggingapi · ec2/vpc/rds/lambda/ecs/eks/
        elbv2/apigateway/s3/cloudfront/route53/... · sts · organizations
```
- **Shared** (`finops_core`): session resolver (profile/env/assume-role), `OrgResolver`
  (accounts + assume_account fan-out), `Config`, `ModelRouter`, hooks, modes, observe, pricing.
- **New** (`devops_core`): `schemas/estate`, `discovery/*` (sources + `EstateScanner`),
  `diagram/*` (`.drawio` builder + render), `tools/*`, `agents/*`, `cli.py`, services (A2A/MCP).
- A new `devops` CLI entry point; a `devops-tools` MCP + `devops-agent` A2A tier in compose.

## 4. Discovery strategy
`EstateScanner.scan(regions, source="auto", accounts=None)` → normalized `Estate`:
1. **Config aggregator** — `configservice` `get-aggregate-discovered-resource-counts` /
   `list-aggregate-discovered-resources`; richest (relationships) when populated. (Empty here → skip.)
2. **Resource Explorer** — `resource-explorer-2 search` per region (query `*`); broad coverage.
3. **Tagging API** — `resourcegroupstaggingapi get-resources`; tagged resources + tags.
4. **Per-service describes** — EC2/VPC/RDS/Lambda/ECS/EKS/ELBv2/API GW/S3/CloudFront/Route53…
   for detail + **relationships** (subnet↔VPC, instance↔subnet/SG, ELB↔targets, …).
Resources are normalized to a common `Resource` shape and deduped by ARN/key. Every unavailable
source becomes a `note` (graceful). **Org fan-out**: for each member account, assume the
read-only role and repeat; accounts without the role are skipped with a note.

## 5. Diagram strategy (per the `drawio` skill)
- Build native **mxGraphModel `.drawio` XML** — never Mermaid/CSV. AWS shapes via the
  `mxgraph.aws4.*` / `shape=mscae/...` style families; group by **Account → VPC → AZ/Subnet →
  resources**; edges for relationships (ENI→subnet, route, peering, ELB→target, LB→service).
- Strict XML: root cells `id=0`/`id=1`, unique ids, escaped chars, **no XML comments**, every
  edge has `<mxGeometry relative="1" as="geometry"/>`.
- **Render** to PNG/SVG: draw.io CLI `drawio -x -f <fmt> -e -b 10 -o out in.drawio` when present;
  a **headless draw.io container** in Docker; **self-contained SVG** fallback (AWS icon SVGs)
  so the dashboard always shows an image. `.drawio` is kept as the editable source of truth.

## 6. Q&A
A `devops-agent` (Strands) over deterministic estate tools: `get_estate_summary`,
`list_resources(service|type|region|account)`, `describe_resource(id)`, `get_topology(vpc)`,
`find_resource(query)`, `get_diagram()`. Numbers/inventory come from tools (exact); the LLM
narrates. Routed via the deterministic `IntentRouter` (new `devops` intents) or the orchestrator.

The bulk inventory is intentionally **thin** (id/type/region/tags) for breadth; **complete** per-
resource detail comes from an **on-demand deep describe** (the drill-down). `describe_resource`
returns the inventory record PLUS a live `detail` via `discovery/details.py`. Coverage, in order:
(1) **special handlers** for awkward APIs (S3 multi-call, SQS url, ECS service, SSM param), (2) a
**broad describe table** across ~30 services (EC2 networking/compute family · ELB · Lambda · RDS ·
DynamoDB · SNS/SQS · ECS/EKS/ECR · IAM · CloudFront · Route53 · KMS · SecretsManager · Step
Functions · ElastiCache · EFS · Kinesis · CloudWatch/Logs · SSM · CloudFormation · AutoScaling ·
Cognito · ACM · EventBridge · CloudTrail · Athena · Backup · AppSync · Bedrock · Amplify · …),
(3) an **AWS Config universal fallback** (any type Config records, when recording is enabled),
(4) a graceful note (inventory + tags) for the deep long tail. Type keys normalize across sources
(`elasticloadbalancing:listener/app` → `:listener`). JSON-safe. On the real estate this resolves
**~77% of resources** (all mainstream services); so the agent answers attachment/orphan/config
questions **definitively** instead of hedging "the inventory doesn't expose X". The dashboard
action panel adds a **🔎 Describe** button surfacing the same detail.

## 7. IAM
Discovery is read-only: AWS managed **`ReadOnlyAccess`** (or **`ViewOnlyAccess`**) suffices; a
tighter explicit policy covers `config:*Aggregate*`, `resource-explorer-2:Search/List*`,
`tag:GetResources`, `ec2:Describe*`, `rds/elasticloadbalancing/lambda/ecs/eks/s3/cloudfront/
route53/apigateway:Describe|List|Get*`, `organizations:ListAccounts`, `sts:AssumeRole`. Fan-out
uses a `DevOpsReadOnly` role per member (ship the policy + a setup script, like FinOps IAM).

## 8. Frontend
- A top-level **product selector** (FinOps | DevOps) in the Streamlit app (sidebar/radio); the
  page renders the chosen product. DevOps page: estate KPIs (accounts/regions/services/resource
  counts), the **diagram** (PNG/SVG + a download for the `.drawio`), an inventory table with
  filters, a **review & debug action panel** (pick a resource from the scanned estate → **🔍 Review**
  / **🩺 Diagnose** buttons — the deterministic fast-path straight to the tool layer, no LLM; fix
  posture follows the sidebar Action mode), and a chat panel routed to the DevOps agent (which can
  also draw/review/diagnose).
- FastAPI gains `/estate/*` (summary, resources, topology), `/diagram` (drawio/png/svg), and
  `/query` already routes by intent.

## 9. Phases
| Phase | Deliverable | Exit criteria |
|---|---|---|
| **1. Discovery engine** | `devops_core` scaffold; `Estate` schema; multi-source `EstateScanner` (Config/RE/Tagging/describes, graceful); `devops scan` CLI | Real estate inventory (counts by service/region) vs console — ✅ **Done**: scanned **870 resources** across 3 regions (RE + Tagging; Config empty → noted); 85 tests |
| **2. Diagram** | `.drawio` builder (AWS shapes) + render (CLI/headless/SVG); `devops diagram` | Valid `.drawio` + PNG/SVG of the estate — ✅ **Done**: native `.drawio` (AWS4 icons, swimlane regions) + CLI-rendered PNG + self-contained SVG of the real 870-resource estate |
| **3. DevOps agent (distributed)** | devops-tools MCP + devops-agent A2A; estate Q&A tools; IntentRouter `devops` intents | Q&A answers about components/topology, distributed — ✅ **Done**: EstateIndex + tools (summary/list/describe/find), devops-tools MCP (:8085) + devops-agent A2A (:9005); answers verified local + in Docker (A2A→MCP) |
| **4. Frontend product selector** | FinOps\|DevOps selector; DevOps dashboard page (KPIs + diagram + inventory + chat); `/estate` + `/diagram` API | Journey: pick DevOps → see estate + diagram + ask — ✅ **Done**: sidebar product selector; DevOps page (KPIs, AWS-icon SVG diagram + .drawio download, filtered inventory, estate chat); verified via AppTest |
| **5. Org fan-out** | assume-role per member; per-account inventory + cross-account topology; `DevOpsReadOnly` policy/script | Multi-account estate map — ✅ **Done**: `scan --org`/`--role-name`, EstateScanner fan-out (assume member role, scan, dedup, graceful notes) + `iam/devops-readonly-policy.json` + setup script. Verified live (mgmt mapped; CT security accounts blocked → noted) |
| **6. Comprehensive coverage + topology** | more services + relationship edges (peering/TGW/endpoints/targets) | Network topology rendered — ✅ **Done**: TopologyScanner (VPC→subnet→instance, IGW/NAT/endpoints, peering) + nested `.drawio` (color-coded public/private subnets, IGW icons, peering edges) + `devops topology` + `get_topology` tool; verified live (3 VPCs / 8 subnets, rendered) |
| **7. Hardening** | sandbox, IAM, accuracy/inventory tests, observability | Sandbox run + green tests — ✅ **Done**: devops tier verified under the hardened sandbox (read-only FS, caps dropped) answering queries; `docs/DEVOPS_IAM.md` (read-only + fan-out role); inventory-consistency tests; 99 tests pass |
| **8. Diagram-on-request** | chat → `draw_diagram` tool (**data-driven** scope from the real estate **or freeform** agent-authored mxGraph per the draw.io skill) → render **PNG/SVG** → surfaced + **downloadable** in the dashboard | Ask "draw me X" in chat → image renders + `.drawio`/`.png`/`.svg` download — ✅ **Done**: `draw_diagram` (estate/topology/vpc/account/service scopes + freeform mxGraph), `builder` + `registry`, dashboard renders SVG inline + 3 downloads; verified live (LLM chose the tool, rendered SVG+PNG); 107 tests |
| **9. Service review & optimization** | `review/` framework: per-service reviewers (live **config + sizing + CloudWatch metrics** + best-practice **RULES**; **Lambda also code** via the lambda-audit skills) → prioritized, **AWS-doc-cited** recommendations; `review_service` tool + `devops review` CLI | "review my lambda `<name>`" → cited findings (config/sizing/code) — ✅ **Done**: rules for lambda/ec2/rds/s3 (+generic Well-Architected fallback), CloudWatch metric snapshot, Lambda code fetch+scan, `review_service` tool + `devops review` CLI; verified live (real Lambda → graviton/tracing findings + code scan; LLM chose the tool). Also fixed the Strands `cache_prompt` deprecation (→ `cache_config`). 120 tests |
| **10. Fault debugging** | `diagnose_service`: config + CloudWatch **metrics/alarms** + recent **Logs** errors + recent **CloudTrail** changes → validate current state → suggest fix; **3 postures** (advisory / artifacts / guarded-write) **user-selectable on the frontend** | "why is `<resource>` failing?" → root-cause + fix in the chosen posture — ✅ **Done**: signal gathering (alarms/Lambda logs/CloudTrail) + correlation rules (timeout/import/throttle/OOM/perms/status-check/storage + recent-change) → ranked hypotheses; posture-shaped fixes (advisory hides cmds, guarded_write gates them behind confirmation, bridged live via `FINOPS_MODE`); `diagnose_service` tool + `devops diagnose` CLI; verified live (CLI + agent). 126 tests |

## 11. DevOps operations (Phases 8–10)
Extends the read-only estate agent into **operations**: diagram-on-request, per-service review/
optimization, and fault debugging. Same rules — read-only by default, exact data from tools, the
LLM narrates; writes only via the existing **modes** (`advisory` → `artifacts` → `guarded_write`).

### 11.1 Diagram-on-request (Phase 8)
A `draw_diagram` **tool** the agent calls from chat (named `draw_*`, not `create_*`, so the
`ReadOnlyGuard` write-prefix heuristic never false-blocks this AWS-read-only, local-artifact tool):
- **Data-driven** — `scope` in {`estate`, `topology`, `vpc:<id>`, `account:<id>`, `service:<svc>`}
  builds the `.drawio` from the **real scanned estate/topology** (reuses `build_drawio` /
  `build_topology_drawio`). Grounded in actual resources.
- **Freeform** — the agent **authors valid `mxGraphModel` XML** (AWS4 shapes, per the draw.io
  skill) and passes it as `drawio_xml`; the tool validates well-formedness, writes, renders.
- **Render** → `.svg` (+`.png` when the draw.io CLI is present; self-contained SVG fallback for
  data-driven). Returns `{drawio, svg, png, svg_content}`.
- **Surfacing** — the tool records the artifact in an in-process `diagram.registry` (the large SVG
  never round-trips the LLM — only a compact path summary does); the dashboard chat reads it after
  the turn, renders the SVG inline, and offers `.drawio`/`.png`/`.svg` **downloads**.

### 11.2 Service review & optimization (Phase 9)
`review/` framework — `review_service(service, resource_id)`:
- **Reviewers** per service (Lambda, EC2, RDS, S3, ECS, … + a **generic** fallback) read **live
  config + sizing + CloudWatch metrics** (read-only) and run curated **best-practice RULES**
  (severity, current vs recommended, **AWS-doc link**). Lambda also **fetches & analyzes code**
  (deployment package) via the `lambda-performance-audit` / `lambda-security-audit` skills.
- **Grounding** = deterministic rules + **LLM narrative** that explains/prioritizes and cites the
  rule/doc — accurate, no heavy RAG. Output is **bounded** (top-N findings) to control tokens.
- Surfaces: `review_service` tool, `devops review <service> <id>` CLI, dashboard action.

### 11.3 Fault debugging (Phase 10)
`diagnose_service(service, resource_id)` — **validate-then-fix**:
- **Signals**: live **config**, **CloudWatch** metrics/alarms, recent **Logs** error patterns,
  recent **CloudTrail** changes (what changed lately). Correlates into a **root-cause** + a fix.
- **Action posture** (reuses `finops_core.modes`, **user-selectable on the frontend**):
  `advisory` (suggest), `artifacts` (generate fix script/IaC, never run), `guarded_write`
  (allowlisted, confirmed, audited apply). Default `advisory`.
- IAM: read-only diagnosis adds `cloudwatch:Get*/Describe*`, `logs:FilterLogEvents/Get*`,
  `cloudtrail:LookupEvents` to the read-only policy; guarded apply needs scoped write per action.

## 10. Conventions
Same as `CLAUDE.md`: read-only by default; TDD (failing test first); every change a PR; no
secrets; exact inventory from tools, not the LLM; reuse `finops_core` shared infra.
