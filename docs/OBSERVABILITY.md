# Observability (OpenTelemetry)

The FinOps + DevSecOps agents emit **traces, metrics, and logs** over OpenTelemetry from every
tier — CLI, A2A sub-agents, MCP tool servers, the orchestrator, the FastAPI gateway, and the
Streamlit dashboard. One pipeline (`finops_core/telemetry.py`) configures sampling, batching, and
PII redaction; an OTEL **Collector** fans the data out to multiple backends. See **SPEC.md §15**.

## Architecture (fan-out)

```
  CLI · A2A agents · MCP tools · orchestrator · API · dashboard
                         │  OTLP (gRPC/HTTP)
                         ▼
                ┌──────────────────────┐
                │   OTEL Collector      │   memory_limiter · batch · redaction ·
                │  (routing / filter)   │   attributes(drop content) · tail_sampling
                └───────┬───────┬───────┘
            traces ─────┘  metrics │  └───── logs
                 ▼            ▼            ▼
            Jaeger UI     Prometheus    debug + file
            (:16686)       (:9090)      (collector)
```

Strands' built-in agent/model/tool spans + meter are routed through the **same** providers, so a
single trace stitches `http.request` / `finops.route.answer` → agent → model invoke → tool call,
across the distributed A2A/MCP hops (W3C trace-context propagation).

## Quick start

```bash
make observability     # base stack + collector + Jaeger + Prometheus
#  Jaeger  → http://localhost:16686      (traces)
#  Prometheus → http://localhost:9090    (metrics: finops_aws_api_calls_total, finops_ce_cost_usd_total,
#                                          finops_llm_tokens_total, gen_ai_* …)
make observability-down
```

Local, no collector (console):

```bash
FINOPS_TELEMETRY=1 FINOPS_TELEMETRY_EXPORTER=console finops ask "where is my money going?"
```

## The five best practices, and how they're implemented

| Practice | Where |
|---|---|
| **Standardize on OTEL** | `setup_telemetry()` builds SDK Tracer/Meter/Logger providers; Strands spans/meter routed through them. OTLP export via the `otel` extra. |
| **Fan-out to many consumers** | The Collector pipelines export each signal to multiple backends (traces → Jaeger+debug+file; metrics → Prometheus+debug; logs → debug+file). |
| **Optimize for volume** | Head sampling (`sample_ratio`) + batching (`BatchSpanProcessor`, periodic metric reader) in-app; **tail_sampling** (keep errors/slow, sample the rest) + `batch` + content-attribute drop in the Collector. |
| **Shift left** | Spans on the deterministic seams (`finops.cost.grouped`, `finops.route.answer`) + `trace_attributes` (intent, tool-call counts) + LLM token/$ metrics let you tune prompts and tool calls from real traces. |
| **Security & privacy** | App-side `RedactingSpanProcessor` (account ids / ARNs / emails on attributes **and** events; content modes) + `RedactingLogFilter`; Collector `redaction` processor as a second pass. |

## Privacy: content modes

Strands records prompts, messages, and tool results (which contain cost figures + account IDs) as
span **events**. `telemetry.content` controls how they're handled — account IDs / ARNs / emails are
**always** redacted in the first two modes:

| Mode | Behavior | Use for |
|---|---|---|
| `omit` *(default)* | Drop content events entirely; redact remaining attributes. | Production / least exposure. |
| `redact` | Keep content events but scrub account ids / ARNs / emails from them. | Prompt-tuning while masking PII. |
| `full` | No in-app scrubbing — rely on the Collector's `redaction` processor. | Trusted debugging; collector enforces redaction. |

## Security & retention (operator responsibilities)

- **Access control.** Jaeger/Prometheus UIs are unauthenticated — do **not** expose `16686`/`9090`
  publicly. Put them behind your network policy / an auth proxy; restrict the collector's OTLP
  ports to the app network.
- **Retention.** Set retention on the backends (Jaeger storage TTL, Prometheus `--storage.tsdb.retention.time`,
  rotation/expiry for the collector's `file` exporter at `/data/telemetry.jsonl`). Keep telemetry
  retention aligned with your data-handling policy.
- **Audit.** The redaction pipeline is two-layer (app + collector). Periodically sample exported
  spans (Jaeger / the file exporter) to confirm no account IDs, ARNs, emails, or prompt content
  leak — especially after enabling `content: redact`/`full` or adding new attributes.
- **Defense-in-depth.** Even in `content: full`, the Collector `redaction` processor masks account
  ids / emails / ARNs before anything reaches a backend.

## Configuration

`config/finops.yaml → telemetry:` (env wins; redacted view at `GET /config`). Key vars:
`FINOPS_TELEMETRY`, `OTEL_EXPORTER_OTLP_ENDPOINT` (or `FINOPS_TELEMETRY_ENDPOINT`),
`FINOPS_TELEMETRY_EXPORTER`, `FINOPS_TELEMETRY_SAMPLE_RATIO`, `FINOPS_TELEMETRY_CONTENT`. Full list
in `.env.example`. Per-service `service.name` is set automatically (`finops-cli`,
`finops-cost-agent`, `finops-api`, `devops-agent`, …).

## Custom signals

- Metrics: `finops.aws.api.calls`, `finops.ce.requests`, `finops.ce.cost.usd`, `finops.llm.tokens`,
  `finops.llm.cost.usd` (FinOps-on-itself) + Strands' `gen_ai.*` agent metrics.
- Spans: `http.request`, `finops.route.answer` (intent routing), `finops.cost.grouped` (the
  deterministic drill-down fast-path) + Strands agent/model/tool spans.
