# AI Agent Marketplace & Multiplexer — Architecture

> **Status:** Conceptual / target architecture (design artifact; not yet built in this repo).
> **Built around:** **Amazon Bedrock AgentCore** (agent / tool / MCP management) + **Amazon Bedrock** (models).
> **Notation:** C4 model (Context → Container → Component → Flow), drawn AWS-native.
> **Date:** 2026-06-21 · **Owner:** Alok Kulkarni

---

## 1. Purpose

Make **AWS AgentCore + Amazon Bedrock the primary control plane** for *all* agents, tools, and
MCP servers across the enterprise — regardless of who built them. A central **Agent Multiplexer**
discovers the right agent for a given **journey** (customer-facing or internal) and routes to it,
whether that agent is AWS-native or comes from **Microsoft Copilot**, **Azure AI Foundry**,
**Atlassian Rovo**, **Dynatrace**, or any other A2A/MCP-capable provider.

Two AgentCore primitives anchor the model:

- **AgentCore Registry** — the catalog where **every** agent, tool, and MCP server is registered
  (capabilities, endpoints, protocol, data-handling, cost/SLA metadata). It is the single source of
  truth the multiplexer queries to decide *who can do this*.
- **AgentCore Identity** — issues a **distinct workload identity per journey/multiplexer instance**
  and manages **inbound** auth (who may call the multiplexer) and **outbound** credentials (how the
  multiplexer authenticates to each downstream provider), federated from the enterprise IdP.

### Design goals
- **Vendor-agnostic** — any provider plugs in through a connector that normalizes it to **A2A**
  (agent-to-agent) and/or **MCP** (tools); no journey code is provider-specific.
- **Journey-scoped & least-privilege** — each journey runs under its own identity; the multiplexer
  can *propose* but agents act only within their granted scope. Read-only by default.
- **One reasoning + governance plane** — all routing/reasoning runs on **Amazon Bedrock** (temp 0
  for deterministic routing), with **Bedrock Guardrails**, and unified **AgentCore Observability**.
- **Clean separation** — experience ≠ routing ≠ capability ≠ provider; each is a replaceable layer.

---

## 2. Locked decisions (from the design interview)

| Decision | Choice |
|---|---|
| **C4 scope** | Full set — **C1 Context, C2 Container, C3 Component, + a runtime Flow** view. |
| **Connectivity** | **AgentCore Gateway (MCP) + A2A, via per-vendor connectors**; everything registered in **AgentCore Registry**. |
| **Multiplexer topology** | **One central multiplexer/router** with per-journey routing policies; **AgentCore Identity issues a workload identity per journey**. |
| **AgentCore primitives** | **Full suite** — Registry, Identity, Runtime, Gateway, Memory, Observability, Browser, Code Interpreter — on top of Amazon Bedrock models/Guardrails/Knowledge Bases. |

---

## 3. The diagrams

All diagrams are in this folder. The editable source is the multi-page
[`ai-marketplace-multiplexer.drawio`](ai-marketplace-multiplexer.drawio); a single multi-page PDF is
[`ai-marketplace-multiplexer.drawio.pdf`](ai-marketplace-multiplexer.drawio.pdf); one PNG per level:

| Level | Diagram | PNG |
|---|---|---|
| **C1** | System Context | [`…-c1-context.drawio.png`](ai-marketplace-multiplexer-c1-context.drawio.png) |
| **C2** | Containers | [`…-c2-containers.drawio.png`](ai-marketplace-multiplexer-c2-containers.drawio.png) |
| **C3** | Multiplexer Components | [`…-c3-components.drawio.png`](ai-marketplace-multiplexer-c3-components.drawio.png) |
| **Flow** | Multiplex a journey (1–11) + onboarding | [`…-flow.drawio.png`](ai-marketplace-multiplexer-flow.drawio.png) |

---

## 4. C1 — System Context

**Actors.** *Customer* (support, sales, self-service) and *Employee / internal user* (DevOps,
FinOps, IT service desk). Both interact only with the platform.

**System.** *AI Agent Marketplace & Multiplexer* (AWS AgentCore + Amazon Bedrock) — registers,
discovers, secures, and routes to agents/tools from any provider, multiplexing the right one into
each journey on demand.

**External systems.**
- **Enterprise IdP** (OAuth2/OIDC SSO) — federates user and workload identity.
- **Agent providers** — Microsoft Copilot, Azure AI Foundry, Atlassian Rovo, Dynatrace agents, and
  "other A2A/MCP agents" (the platform is extensible by design).

**Key relationships.** Actors drive journeys over HTTPS/chat/voice/Slack/Teams/IDE; the platform
federates identity with the IdP and **discovers & invokes registered agents over A2A/MCP via
AgentCore**.

---

## 5. C2 — Containers

A strict top-to-bottom flow keeps the diagram readable (no crossing lines):

1. **Experience layer** — *Customer Experiences* (web, mobile, portal, contact center/IVR) and
   *Employee Experiences* (Slack, Teams, IDE, IT service desk).
2. **Journey API & Intake** — API Gateway + authN + session + journey-context capture. Single entry
   for every channel.
3. **Agent Multiplexer / Router** *(the heart)* — routing, capability/policy matching, identity
   brokering, and A2A & MCP adapters. Selects the right **registered** agent per journey and reasons
   on Amazon Bedrock at temperature 0.
4. **Amazon Bedrock + AgentCore** *(management platform)* — the full suite as sibling containers:
   - **Amazon Bedrock** — models, **Guardrails**, **Knowledge Bases**.
   - **AgentCore Registry** — agent/tool/MCP catalog.
   - **AgentCore Identity** — workload identity, OAuth, inbound/outbound auth.
   - **AgentCore Runtime** — serverless hosting for AWS-native agents (e.g., the FinOps/DevOps agents).
   - **AgentCore Gateway** — turns APIs/Lambda into **MCP** tools.
   - **AgentCore Memory** — short / long-term context.
   - **AgentCore Observability** — traces & metrics (→ Amazon CloudWatch).
   - **AgentCore Browser** & **Code Interpreter** — managed tools available to agents.
5. **Provider Connectors & Normalization** — per-vendor A2A/MCP adapters mapping each provider to a
   common contract.
6. **External providers** — Copilot, Azure AI Foundry, Atlassian Rovo, Dynatrace (outside the
   boundary), plus the **Enterprise IdP** and **CloudWatch** sinks.

**Relationship summary.** Experiences → Journey API → Multiplexer. The multiplexer uses Registry
(*discover*), Identity (*authZ*), Runtime (*AWS-native agents*), Gateway (*MCP tools*), Memory
(*context*) and Observability (*trace*). External agents are reached **Gateway → Connectors**
(MCP) and **Runtime → Connectors** (A2A), then **Connectors → each provider**. Identity federates to
the IdP; Observability emits to CloudWatch.

---

## 6. C3 — Agent Multiplexer components

Inside the multiplexer, a clean pipeline with two supporting wings:

- **Journey Context API** → **Intent & Journey Classifier** (Bedrock; customer-facing vs internal)
  → **Routing Policy Engine** (capability · cost · SLA · data-residency rules) → **Capability
  Matcher / Agent Selector**.
- **Registry Client** (left) feeds the matcher *candidate* agents from **AgentCore Registry**.
- **Identity Broker** (right) feeds the matcher a *scoped token* (per-journey workload identity +
  outbound creds) from **AgentCore Identity**.
- The matcher dispatches to the **A2A Client** and/or **MCP Client** (via AgentCore Gateway), whose
  results feed the **Response Aggregator / Multiplexer Core** (merges results, enforces **Bedrock
  Guardrails**).
- The whole container **uses the AgentCore + Bedrock platform** (Registry, Identity, Gateway,
  Runtime, Memory, Observability, Bedrock) and performs **A2A/MCP egress** through Provider
  Connectors.

Component → platform mapping (described here to keep the diagram clean): Registry Client→Registry,
Identity Broker→Identity, MCP Client→Gateway, Memory manager→Memory, telemetry→Observability,
classifier→Bedrock.

---

## 7. Flow — multiplexing a journey

**Runtime (steps 1–11).**
1. User issues a journey request → **Journey API**.
2. API forwards normalized **journey context** → **Multiplexer**.
3. Multiplexer **discovers capable agents** ← AgentCore **Registry**.
4. Multiplexer obtains a **per-journey identity / token** ← AgentCore **Identity**.
5. Multiplexer **invokes** the selected agent **[A2A / MCP]** → AgentCore **Gateway**.
6. Gateway makes the **normalized call** → **Provider Connector**.
7. Connector makes the **provider call** → **Provider Agent** (Copilot / Foundry / Rovo / Dynatrace).
8–10. Cross-cutting: Multiplexer reads/writes **Memory** (context), emits **Observability** (trace),
   and uses **Amazon Bedrock** for route reasoning.
11. The **aggregated, guardrailed response** returns to the user.

**Onboarding (one-time).** A provider agent is **exposed** to a connector → the connector
**registers** it (A2A/MCP, capabilities, endpoints) in **AgentCore Registry** → **AgentCore
Identity** **provisions** its workload identity and outbound credentials. After this, the agent is
discoverable and routable in any journey.

---

## 8. Identity & security model

- **Per-journey workload identity.** AgentCore Identity mints a distinct identity for each
  journey/multiplexer instance; downstream calls carry **scoped, short-lived** credentials. A
  customer-support journey cannot use an internal-FinOps journey's grants.
- **Inbound vs outbound auth.** Inbound: the IdP authenticates the user and the Journey API
  authorizes the request. Outbound: the Identity Broker exchanges for provider-specific credentials
  (OAuth client creds / token exchange) per connector.
- **Guardrails everywhere.** Bedrock Guardrails (PII, prompt-injection, content policy) wrap routing
  and aggregation; provider data is treated as **data, not instructions**.
- **Least privilege & read-only default.** Write/actuating capabilities are opt-in, scoped, and
  audited — consistent with the FinOps/DevOps agents' posture in this repo.
- **Full traceability.** Every hop is traced through AgentCore Observability → CloudWatch, giving
  per-journey cost, latency, and which agent served which step.

---

## 9. Why this shape

- **Registry-driven routing** decouples journeys from providers: add/retire an agent by changing the
  catalog, not the journeys.
- **One multiplexer, many journeys** keeps routing policy, identity brokering, and guardrails in a
  single governed place while still issuing per-journey identities.
- **A2A + MCP via connectors** is the realistic interop story: full agents over A2A, tools over MCP,
  each vendor normalized once.
- **AgentCore as the platform** means agent hosting (Runtime), tool exposure (Gateway), identity,
  memory, and observability are managed AWS primitives rather than bespoke plumbing.

---

## 10. Extensibility & open questions

**Extensibility.** New providers = new connector + Registry entry + Identity provisioning. New
journeys = new routing policy + identity; no platform change.

**Open questions (non-blocking, for refinement):**
1. Is the multiplexer **synchronous** (request/response) only, or also **event-driven** (async
   journeys, long-running agents)?
2. Routing policy authority — static rules, a learned router, or a hybrid (rules + Bedrock)?
3. Multi-agent **composition** within one journey (fan-out + merge) vs single best-agent selection —
   how far in v1?
4. Data residency / sovereignty constraints per provider (e.g., keep certain journeys AWS-only)?
5. Billing/showback model for cross-provider usage (who pays for a Copilot call inside a journey)?

---

*Generated as an architecture artifact. Diagrams are native `.drawio` (AWS shapes, C4 notation);
PNG/PDF exports embed the diagram XML and remain editable in draw.io.*
