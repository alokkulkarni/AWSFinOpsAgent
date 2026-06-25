"""OpenTelemetry observability — one standard pipeline for traces, metrics, and logs.

Design (see docs/OBSERVABILITY.md):
- **Standardize on OTEL.** ``setup_telemetry`` builds SDK Tracer/Meter/Logger providers and hooks
  Strands' built-in agent/model/tool spans + meter into the *same* providers, so the whole
  estate (CLI, A2A agents, MCP tool servers, orchestrator, API, dashboard) emits correlated
  telemetry. Idempotent — safe to call from every entrypoint.
- **Optimize for volume.** Head sampling (``ParentBased(TraceIdRatioBased)``) + batching
  (``BatchSpanProcessor`` / periodic metric reader / ``BatchLogRecordProcessor``). Heavier
  filtering + tail sampling live in the OTEL Collector (the fan-out/routing layer).
- **Security & privacy.** A ``RedactingSpanProcessor`` scrubs account IDs / ARNs / emails from
  span attributes *and* events, and (content mode ``omit``) drops prompt/response/tool-result
  content events entirely. Logs get the same redaction via ``RedactingLogFilter``. The Collector
  applies a second redaction pass (defense-in-depth).

``opentelemetry-sdk`` ships with the ``agent`` extra (Strands); the OTLP exporter comes from the
``otel`` extra. This module imports the OTEL *API/SDK* (always present); the OTLP *exporter* is
imported lazily so a console/disabled run needs no exporter package.
"""
from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional

from finops_core.config import Config

# --- redaction (PII): 12-digit AWS account ids + emails (ARNs embed the account id) ----------
_ACCOUNT_RE = re.compile(r"\d{12}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_MASK = "************"
# A span event carries conversation content when its name is a gen_ai semantic-convention event
# or otherwise names a message/prompt/completion/choice. Operational events (exception) are kept.
_CONTENT_MARKERS = ("message", "prompt", "completion", "choice")


def redact_text(s):
    """Mask account ids + emails in a string (no-op for non-strings)."""
    if not isinstance(s, str):
        return s
    return _ACCOUNT_RE.sub(_MASK, _EMAIL_RE.sub("***@***", s))


def redact_attrs(attrs: dict) -> dict:
    """Redact every string value in an attribute mapping; leave non-strings untouched."""
    return {k: (redact_text(v) if isinstance(v, str) else v) for k, v in attrs.items()}


def _is_content_event(name: str) -> bool:
    n = (name or "").lower()
    return n.startswith("gen_ai.") or any(m in n for m in _CONTENT_MARKERS)


def resolve_service_name(cfg: Config, default: str) -> str:
    """Config override wins, else the per-entrypoint default (e.g. ``finops-cost-agent``)."""
    return getattr(cfg.telemetry, "service_name", None) or default


# --- the redaction span processor (runs before the batch exporter) ---------------------------
try:  # SpanProcessor base needs the SDK; present via the agent/otel extras.
    from opentelemetry.sdk.trace import SpanProcessor as _SpanProcessor
except Exception:  # pragma: no cover - SDK always present in this project
    _SpanProcessor = object  # type: ignore


class RedactingSpanProcessor(_SpanProcessor):
    """Scrub PII (and optionally drop content) in place, before the batch exporter sees the span.

    Registered FIRST on the provider so the same span object — mutated here — is what the
    ``BatchSpanProcessor`` exports. ``content``: ``omit`` (drop content events + redact),
    ``redact`` (keep content, scrub it), ``full`` (no in-app scrubbing; rely on the collector).
    """

    def __init__(self, content_mode: str = "omit", redact: bool = True):
        self.content_mode = content_mode
        self.redact = redact

    def on_start(self, span, parent_context=None):  # noqa: D401
        return None

    def on_end(self, span) -> None:
        # OTEL span/event attributes are immutable BoundedAttributes, so we rebuild rather than
        # mutate in place (span.attributes reads from span._attributes; events are replaced).
        if self.content_mode == "full":
            return
        if self.redact:
            attrs = getattr(span, "_attributes", None)
            if attrs:
                span._attributes = redact_attrs(dict(attrs))
        events = list(getattr(span, "_events", None) or [])
        if self.content_mode == "omit":
            events = [e for e in events if not _is_content_event(e.name)]
        if events and (self.content_mode in ("omit", "redact")) and self.redact:
            events = [self._redact_event(e) for e in events]
        if self.content_mode in ("omit", "redact"):
            span._events = events

    @staticmethod
    def _redact_event(ev):
        from opentelemetry.sdk.trace import Event
        return Event(name=ev.name, attributes=redact_attrs(dict(ev.attributes or {})),
                     timestamp=ev.timestamp)

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class RedactingLogFilter(logging.Filter):
    """Redact account ids / emails from log records before they're exported or printed."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_text(record.getMessage())
            record.args = ()
        except Exception:  # pragma: no cover - never let logging redaction break logging
            pass
        return True


# --- metrics instruments (FinOps-specific; Strands emits the gen_ai/agent metrics) -----------
@dataclass
class _Instruments:
    aws_api_calls: object
    ce_requests: object
    ce_cost_usd: object
    llm_tokens: object
    llm_cost_usd: object


_INSTRUMENTS: dict = {}


def instruments(meter=None) -> Optional[_Instruments]:
    """Lazily create + cache the FinOps OTEL instruments on ``meter`` (default: global meter).

    Returns ``None`` if the metrics API is unavailable, so callers can stay best-effort.
    """
    try:
        from opentelemetry import metrics as _metrics
    except Exception:  # pragma: no cover
        return None
    m = meter or _metrics.get_meter("finops")
    key = id(m)
    inst = _INSTRUMENTS.get(key)
    if inst is None:
        inst = _Instruments(
            aws_api_calls=m.create_counter("finops.aws.api.calls", unit="1",
                                           description="AWS API calls made by the agent"),
            ce_requests=m.create_counter("finops.ce.requests", unit="1",
                                         description="Cost Explorer requests (billed ~$0.01 each)"),
            ce_cost_usd=m.create_counter("finops.ce.cost.usd", unit="USD",
                                         description="Estimated Cost Explorer spend incurred"),
            llm_tokens=m.create_counter("finops.llm.tokens", unit="1",
                                        description="LLM tokens by type"),
            llm_cost_usd=m.create_counter("finops.llm.cost.usd", unit="USD",
                                          description="Estimated LLM spend"),
        )
        _INSTRUMENTS[key] = inst
    return inst


def record_llm_usage(usage: dict) -> None:
    """Emit token + cost metrics from a ``pricing.usage_summary`` dict (best-effort)."""
    inst = instruments()
    if not inst or not usage:
        return
    model = usage.get("model", "?")
    for kind, key in (("input", "input_tokens"), ("output", "output_tokens"),
                      ("cache_read", "cache_read_tokens"), ("cache_write", "cache_write_tokens")):
        n = int(usage.get(key, 0) or 0)
        if n:
            inst.llm_tokens.add(n, {"model": model, "type": kind})
    if usage.get("estimated_usd"):
        inst.llm_cost_usd.add(float(usage["estimated_usd"]), {"model": model})


@contextmanager
def traced(name: str, **attrs):
    """A span around a deterministic engine seam (shift-left). Attribute values must be metadata,
    never raw cost data. Best-effort: yields ``None`` if tracing isn't configured."""
    try:
        from opentelemetry import trace as _trace
    except Exception:  # pragma: no cover
        yield None
        return
    tracer = _trace.get_tracer("finops")
    with tracer.start_as_current_span(name) as span:
        for k, v in attrs.items():
            if v is not None:
                span.set_attribute(k, v)
        yield span


# --- bootstrap -------------------------------------------------------------------------------
@dataclass
class TelemetryHandle:
    service_name: str
    exporter: str
    tracer_provider: object = None
    meter_provider: object = None
    logger_provider: object = None


_STATE: Optional[TelemetryHandle] = None


def _version() -> str:
    try:
        import importlib.metadata as _m
        return _m.version("aws-finops-agent")
    except Exception:
        return "0.1.0"


def _resolve_exporter(t, default_console: bool) -> str:
    """auto → otlp if an endpoint is configured, else console (servers) / none (one-shot CLI)."""
    if t.exporter in ("otlp", "console", "none"):
        return t.exporter
    if t.endpoint:
        return "otlp"
    return "console" if default_console else "none"


def setup_telemetry(cfg: Optional[Config] = None, service_name: str = "finops", *,
                    default_console: bool = False, set_global: bool = True
                    ) -> Optional[TelemetryHandle]:
    """Initialize OTEL traces/metrics/logs. Idempotent; returns ``None`` when disabled / no exporter.

    default_console: for long-running services (serve/api/dashboard) — emit to console when no
                     OTLP endpoint is set. One-shot CLI passes False so it stays quiet.
    set_global: install the providers as the OTEL globals (real runtime). Tests pass False.
    """
    global _STATE
    cfg = cfg or Config.load()
    t = cfg.telemetry
    if not t.enabled:
        return None
    mode = _resolve_exporter(t, default_console)
    if mode == "none":
        return None
    if _STATE is not None:
        return _STATE
    handle = _build(cfg, resolve_service_name(cfg, service_name), mode, set_global)
    _STATE = handle
    return handle


def _build(cfg: Config, service_name: str, mode: str, set_global: bool) -> TelemetryHandle:
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({
        "service.name": service_name,
        "service.version": _version(),
        "deployment.environment": os.getenv("FINOPS_ENV", "local"),
    })
    t = cfg.telemetry
    tp = _tracer_provider(cfg, resource, mode) if t.traces else None
    mp = _meter_provider(cfg, resource, mode) if t.metrics else None
    lp = _logger_provider(cfg, resource, mode) if t.logs else None
    if set_global:
        _install_global(tp, mp, lp, cfg)
    return TelemetryHandle(service_name, mode, tp, mp, lp)


def _tracer_provider(cfg, resource, mode):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    tp = TracerProvider(resource=resource,
                        sampler=ParentBased(TraceIdRatioBased(cfg.telemetry.sample_ratio)))
    tp.add_span_processor(RedactingSpanProcessor(  # FIRST: mutate before the batch exporter reads
        cfg.telemetry.content, redact=cfg.guardrails.redact_account_ids))
    exporter = ConsoleSpanExporter() if mode == "console" else _otlp("trace", cfg)
    tp.add_span_processor(BatchSpanProcessor(exporter))
    return tp


def _meter_provider(cfg, resource, mode):
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader

    exporter = ConsoleMetricExporter() if mode == "console" else _otlp("metric", cfg)
    return MeterProvider(resource=resource,
                         metric_readers=[PeriodicExportingMetricReader(exporter)])


def _logger_provider(cfg, resource, mode):
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs import export as _log_export

    lp = LoggerProvider(resource=resource)
    # ConsoleLogRecordExporter is the current name; fall back for older SDKs.
    console_log = getattr(_log_export, "ConsoleLogRecordExporter", None) or _log_export.ConsoleLogExporter
    exporter = console_log() if mode == "console" else _otlp("log", cfg)
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    lp.add_log_record_processor(BatchLogRecordProcessor(exporter))
    return lp


def _otlp(signal: str, cfg):
    """Construct the OTLP exporter for a signal (grpc default, http optional). Lazy import keeps
    console/disabled runs free of the exporter package."""
    http = cfg.telemetry.protocol == "http"
    endpoint = cfg.telemetry.endpoint  # None → SDK falls back to OTEL_EXPORTER_OTLP_* envs
    if signal == "trace":
        mod = ("opentelemetry.exporter.otlp.proto.http.trace_exporter" if http
               else "opentelemetry.exporter.otlp.proto.grpc.trace_exporter")
        cls = "OTLPSpanExporter"
    elif signal == "metric":
        mod = ("opentelemetry.exporter.otlp.proto.http.metric_exporter" if http
               else "opentelemetry.exporter.otlp.proto.grpc.metric_exporter")
        cls = "OTLPMetricExporter"
    else:
        mod = ("opentelemetry.exporter.otlp.proto.http._log_exporter" if http
               else "opentelemetry.exporter.otlp.proto.grpc._log_exporter")
        cls = "OTLPLogExporter"
    exporter_cls = getattr(__import__(mod, fromlist=[cls]), cls)
    return exporter_cls(endpoint=endpoint) if endpoint else exporter_cls()


def _install_global(tp, mp, lp, cfg) -> None:
    from opentelemetry import metrics as _metrics
    from opentelemetry import trace as _trace

    if tp is not None:
        _trace.set_tracer_provider(tp)
    if mp is not None:
        _metrics.set_meter_provider(mp)
    if lp is not None:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.sdk._logs import LoggingHandler

        set_logger_provider(lp)
        handler = LoggingHandler(logger_provider=lp)
        handler.addFilter(RedactingLogFilter())
        for name in ("finops", "devops", "strands"):
            logging.getLogger(name).addHandler(handler)
    # Route Strands' agent/model/tool spans through our provider + install trace-context
    # propagators so trace ids flow across the distributed A2A/MCP hops. Best-effort.
    try:  # pragma: no cover - exercised at runtime, not in unit tests
        from strands.telemetry import StrandsTelemetry
        StrandsTelemetry(tracer_provider=tp)
    except Exception:
        pass


def reset_telemetry() -> None:
    """Clear the idempotency cache (tests/process re-init)."""
    global _STATE
    _STATE = None
    _INSTRUMENTS.clear()
