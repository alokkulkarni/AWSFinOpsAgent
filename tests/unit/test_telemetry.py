"""OpenTelemetry observability: config gating, PII redaction (the security/privacy bar), the
redacting span processor (attributes + content events), idempotent setup, and the AWS-API meter's
OTEL counter emission."""
import logging

import pytest

from finops_core.config import Config
from finops_core import telemetry as tel


# --- config ----------------------------------------------------------------
def test_telemetry_defaults():
    cfg = Config()
    assert cfg.telemetry.enabled is True
    assert cfg.telemetry.exporter == "auto"
    assert cfg.telemetry.content == "omit"        # privacy-safe default
    assert cfg.telemetry.sample_ratio == 1.0


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("FINOPS_TELEMETRY", "false")
    monkeypatch.setenv("FINOPS_TELEMETRY_CONTENT", "full")
    monkeypatch.setenv("FINOPS_TELEMETRY_SAMPLE_RATIO", "0.25")
    monkeypatch.setenv("FINOPS_TELEMETRY_ENDPOINT", "http://collector:4317")
    cfg = Config.load()
    assert cfg.telemetry.enabled is False
    assert cfg.telemetry.content == "full"
    assert cfg.telemetry.sample_ratio == 0.25
    assert cfg.telemetry.endpoint == "http://collector:4317"


def test_otel_endpoint_env_is_honored(monkeypatch):
    monkeypatch.delenv("FINOPS_TELEMETRY_ENDPOINT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel:4317")
    assert Config.load().telemetry.endpoint == "http://otel:4317"


def test_redacted_config_exposes_telemetry():
    red = Config().redacted()
    assert "telemetry" in red and red["telemetry"]["enabled"] is True


# --- redaction (PII: account ids, ARNs, emails) ----------------------------
def test_redact_text_masks_account_id():
    assert tel.redact_text("spend on 123456789012 today") == "spend on ************ today"


def test_redact_text_masks_email():
    out = tel.redact_text("ping someone@example.com please")
    assert "someone@example.com" not in out and "@" in out


def test_redact_text_leaves_clean_text():
    assert tel.redact_text("EC2 is the top spender") == "EC2 is the top spender"


def test_redact_attrs_only_touches_strings():
    out = tel.redact_attrs({"acct": "123456789012", "count": 5})
    assert out["acct"] == "************" and out["count"] == 5


# --- redacting span processor (attributes + content events) ----------------
def _span_through(processor, *, attrs, events):
    """Run a finished span through `processor` (first) + a capturing exporter (second)."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter

    captured = {}

    class Cap(SpanExporter):
        def export(self, spans):
            captured["span"] = spans[0]
            return 0

        def shutdown(self):
            pass

    tp = TracerProvider()
    tp.add_span_processor(processor)            # mutates in place first
    tp.add_span_processor(SimpleSpanProcessor(Cap()))
    tr = tp.get_tracer("t")
    with tr.start_as_current_span("s") as sp:
        for k, v in attrs.items():
            sp.set_attribute(k, v)
        for name, eattrs in events:
            sp.add_event(name, eattrs)
    return captured["span"]


def test_processor_omit_drops_content_events_and_redacts_attrs():
    s = _span_through(
        tel.RedactingSpanProcessor(content_mode="omit", redact=True),
        attrs={"aws.account_id": "123456789012", "count": 7},
        events=[("gen_ai.user.message", {"content": "acct 123456789012"}),
                ("exception", {"exception.type": "Boom"})],
    )
    assert s.attributes["aws.account_id"] == "************"
    assert s.attributes["count"] == 7
    names = [e.name for e in s.events]
    assert "gen_ai.user.message" not in names   # content event dropped
    assert "exception" in names                 # operational event kept


def test_processor_redact_keeps_content_but_scrubs_it():
    s = _span_through(
        tel.RedactingSpanProcessor(content_mode="redact", redact=True),
        attrs={"x": "ok"},
        events=[("gen_ai.user.message", {"content": "acct 123456789012"})],
    )
    ev = [e for e in s.events if e.name == "gen_ai.user.message"][0]
    assert ev.name == "gen_ai.user.message"      # kept
    assert "123456789012" not in ev.attributes["content"]  # but scrubbed


def test_processor_full_leaves_everything():
    s = _span_through(
        tel.RedactingSpanProcessor(content_mode="full", redact=True),
        attrs={"aws.account_id": "123456789012"},
        events=[("gen_ai.user.message", {"content": "acct 123456789012"})],
    )
    assert s.attributes["aws.account_id"] == "123456789012"   # passthrough (collector handles)
    assert any(e.name == "gen_ai.user.message" for e in s.events)


# --- setup_telemetry (idempotent, safe no-ops) -----------------------------
def test_setup_disabled_returns_none():
    cfg = Config()
    cfg.telemetry.enabled = False
    assert tel.setup_telemetry(cfg, "finops-test", set_global=False) is None


def test_setup_console_does_not_raise_and_is_idempotent():
    cfg = Config()
    cfg.telemetry.exporter = "console"
    h1 = tel.setup_telemetry(cfg, "finops-test", set_global=False)
    h2 = tel.setup_telemetry(cfg, "finops-test", set_global=False)
    assert h1 is not None and h1 is h2          # idempotent


def test_service_name_resolution():
    assert tel.resolve_service_name(Config(), "finops-cli") == "finops-cli"
    cfg = Config()
    cfg.telemetry.service_name = "custom"
    assert tel.resolve_service_name(cfg, "finops-cli") == "custom"


# --- AWS-API meter emits an OTEL counter -----------------------------------
def test_api_meter_emits_otel_counter():
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    from finops_core.observe import ApiMeter

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("finops")

    m = ApiMeter(meter=meter)
    m.record("ce", "GetCostAndUsage")
    m.record("ce", "GetCostForecast")

    data = reader.get_metrics_data()
    points = [
        (metric.name, dp)
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for metric in sm.metrics
        for dp in metric.data.data_points
    ]
    names = {name for name, _ in points}
    assert "finops.aws.api.calls" in names
    # summary() still works (backward compatible with GET /metrics)
    assert m.summary()["ce_requests"] == 2


def test_setup_logging_redaction_filter():
    """Logs must not leak account ids either."""
    rec = logging.LogRecord("finops", logging.INFO, __file__, 1,
                            "charged on account 123456789012", None, None)
    assert tel.RedactingLogFilter().filter(rec) is True
    assert "123456789012" not in rec.getMessage()
