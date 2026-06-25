# Conversation memory & summarization

The FinOps and DevSecOps (estate) agents manage their own context so long conversations stay
cheap, fast, and crash-free, and so durable learnings survive across sessions. Two independent,
**on-by-default** mechanisms, both built on the Strands Agents SDK. See **SPEC.md §5.5**.

> **Both are *context*, never the source of figures.** Exact numbers always come from the
> deterministic tool layer (numbers-must-be-exact). Summaries preserve figures verbatim; recalled
> memory is treated as **data, not instructions** (same prompt-injection posture as SPEC §14).

## 1. Summarization (the context-rot fix)

Long-lived agents (the dashboard chat reuses one cached `Agent` across every turn; the A2A
servers hold one for the process lifetime) would otherwise re-send the full raw transcript to
Bedrock every turn — rising cost/latency and an eventual context-window overflow that crashes the
turn. Instead we attach a Strands [`SummarizingConversationManager`](https://strandsagents.com/docs/user-guide/concepts/agents/conversation-management/):
the oldest turns are folded into a compact running summary while recent turns stay verbatim.

- **Automatic & non-interrupting** — it runs *inside* the event loop: proactively via a
  `BeforeModelCall` threshold hook (compress at 70% of the context window) and reactively on
  overflow. The user never sees it happen.
- vs. the Strands default `SlidingWindowConversationManager`, which simply **drops** old
  messages (lossy). We summarize instead so earlier context isn't lost.
- Lives in `finops_core/conversation.py` (`build_conversation_manager`). The summary prompt
  explicitly preserves exact figures, periods, and identifiers.

## 2. Persistent memory (recall + capture of "important aspects")

A local, file-backed Strands [`MemoryManager`](https://strandsagents.com/docs/user-guide/concepts/agents/memory/)
store gives each agent durable, cross-session memory:

- **Recall (injection)** — relevant memories are auto-injected into each new prompt, so the agent
  can refer to / validate against what it learned before.
- **Capture — both modes:**
  - *Automatic extraction* — a (cheap) model distills salient facts from the conversation every
    few turns and stores them.
  - *Explicit tool* — the agent can call a "remember this" tool to save a fact on demand.
- **Search tool** — the agent can query memory to validate a new prompt against prior context.

Lives in `finops_core/memory/` — `store.py` (`LocalJSONMemoryStore`, token-overlap search, no
embeddings/infra) + `__init__.py` (`attach_memory`). Per-agent namespaces keep them separate:
`finops` (cost/optimize/anomaly/orchestrator) and `devops` (estate).

### Where it's stored & privacy

- Default location: `~/.finops_agent/memory/<namespace>.json` — **outside the repo** by design.
- **AWS account IDs (12-digit) are redacted on write** by default, honoring
  `guardrails.redact_account_ids`. `.gitignore` also covers in-repo override paths.
- To wipe memory, delete the namespace JSON file (or the whole `~/.finops_agent/memory/` dir).

## Configuration

`config/finops.yaml` (env wins; redacted view at `GET /config`):

```yaml
conversation:
  summarize: true            # FINOPS_CONVERSATION_SUMMARIZE
  preserve_recent: 10        # FINOPS_CONVERSATION_PRESERVE_RECENT — recent turns kept verbatim
  summary_ratio: 0.3         # fraction of removable history folded into the summary
  proactive_threshold: 0.7   # compress at this context-window usage; <=0 → reactive-only
  summarizer_role: null      # model role to summarize with (null = the agent's own model)
memory:
  enabled: true              # FINOPS_MEMORY
  dir: ~/.finops_agent/memory # FINOPS_MEMORY_DIR
  max_search_results: 5
  auto_extract: true         # LLM distills salient facts each interval
  allow_write_tool: true     # also expose an explicit "remember this" tool
```

**Per-call overrides** (tri-state; `None` → config default):

- CLI: `finops ask` / `devops ask` accept `--memory/--no-memory` and `--summarize/--no-summarize`.
- Dashboard: sidebar **"Conversation memory"** and **"Summarize long chats"** toggles (FinOps + DevOps).
- Code: `build_cost_agent(..., memory=False, conversation=False)` (same for optimize/anomaly/estate).

Turning both off reverts each agent to byte-for-byte prior behavior (no `memory_manager`, Strands'
default sliding window).

## How it fits the agent factories

`finops_core/agent_context.py::agent_context_kwargs(cfg, namespace, router=, conversation=, memory=)`
returns `{conversation_manager?, memory_manager?}`, which every `build_*_agent` factory (and the
inline orchestrator) splats into `Agent(...)` alongside `**skill_kwargs` — the same
`attach_skills` convention. An empty/partial dict when a capability is off keeps default paths
unchanged.
