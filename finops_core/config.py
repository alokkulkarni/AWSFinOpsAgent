"""Configuration: YAML (config/*.yaml) + environment overrides (env wins).

Loading order: defaults -> finops.yaml -> models.yaml (model IDs) -> env (FINOPS_*, AWS_*).
PyYAML is optional; without it (or without the files) we fall back to defaults + env so the
Phase-0 preflight still runs.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:  # PyYAML is optional
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "finops.yaml"
DEFAULT_MODELS_PATH = REPO_ROOT / "config" / "models.yaml"

_TRUE = {"1", "true", "yes", "on"}
_ACCOUNT_RE = re.compile(r"\d{12}")


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    return default if val is None else val.strip().lower() in _TRUE


def _first_env(*names: str) -> Optional[str]:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return None


def _mask_arn(arn: Optional[str]) -> Optional[str]:
    return None if not arn else _ACCOUNT_RE.sub("************", arn)


@dataclass
class AwsConfig:
    auth: str = "profile"            # profile | env | assume_role
    profile: str = "default"
    region: str = "us-east-1"        # operational region (Compute Optimizer, Athena, ...)
    ce_region: str = "us-east-1"     # Cost Explorer / Budgets endpoint region
    org_mode: bool = False
    assume_base: str = "env"         # base creds for assume_role: env | profile
    role_arn: Optional[str] = None
    role_session_name: str = "finops-agent"
    external_id: Optional[str] = None


@dataclass
class LlmConfig:
    provider: str = "bedrock"        # bedrock | anthropic
    region: str = "us-east-1"
    roles: dict = field(default_factory=dict)
    fallback: list = field(default_factory=list)
    temperature: float = 0.0         # 0 = most deterministic (exact-number relay)
    max_tokens: int = 2048           # ALWAYS explicit — unset over-reserves Bedrock quota
    cache_prompt: bool = True        # Bedrock prompt caching (system prompt)
    cache_tools: bool = True         # Bedrock prompt caching (tool definitions)
    guardrail_id: Optional[str] = None       # Bedrock Guardrail (PII / denied topics); off by default
    guardrail_version: str = "DRAFT"
    guardrail_trace: str = "enabled"


@dataclass
class GuardrailsConfig:
    athena_max_scanned_gb: int = 10
    require_confirmation: bool = True
    redact_account_ids: bool = True


@dataclass
class TelemetryConfig:
    """OpenTelemetry export (traces, metrics, logs). ON by default — falls back to console when no
    collector endpoint is configured, so there's no export noise locally. See docs/OBSERVABILITY.md.
    """
    enabled: bool = True
    exporter: str = "auto"            # auto | otlp | console | none (auto: otlp if endpoint else console)
    endpoint: Optional[str] = None    # OTLP endpoint (else OTEL_EXPORTER_OTLP_ENDPOINT)
    protocol: str = "grpc"            # grpc | http
    service_name: Optional[str] = None  # default = per-entrypoint name passed to setup_telemetry
    sample_ratio: float = 1.0         # trace head-sampling ratio (volume control); 1.0 = all
    traces: bool = True
    metrics: bool = True
    logs: bool = True
    content: str = "omit"             # omit | redact | full — how prompt/response/tool content is handled


@dataclass
class Config:
    mode: str = "advisory"           # advisory | artifacts | guarded_write
    aws: AwsConfig = field(default_factory=AwsConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    guardrails: GuardrailsConfig = field(default_factory=GuardrailsConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    cache_ttl_seconds: int = 3600
    skills_enabled: bool = False     # agent skills (progressive disclosure); opt-in, off by default

    # ---- loading -------------------------------------------------------
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        data: dict = {}
        models: dict = {}
        cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
        if yaml and cfg_path.exists():
            data = yaml.safe_load(cfg_path.read_text()) or {}
        if yaml and DEFAULT_MODELS_PATH.exists():
            models = yaml.safe_load(DEFAULT_MODELS_PATH.read_text()) or {}

        cfg = cls()
        cfg.mode = data.get("mode", cfg.mode)
        cfg.cache_ttl_seconds = (data.get("cache") or {}).get("ttl_seconds", cfg.cache_ttl_seconds)
        cfg.skills_enabled = bool((data.get("skills") or {}).get("enabled", cfg.skills_enabled))

        aws = data.get("aws") or {}
        cfg.aws = AwsConfig(
            auth=aws.get("auth", cfg.aws.auth),
            profile=aws.get("profile", cfg.aws.profile),
            region=aws.get("region", cfg.aws.region),
            ce_region=aws.get("ce_region", cfg.aws.ce_region),
            org_mode=bool(aws.get("org_mode", cfg.aws.org_mode)),
            assume_base=aws.get("assume_base", cfg.aws.assume_base),
            role_arn=aws.get("role_arn", cfg.aws.role_arn),
            role_session_name=aws.get("role_session_name", cfg.aws.role_session_name),
            external_id=aws.get("external_id", cfg.aws.external_id),
        )

        llm = data.get("llm") or {}
        merged_roles = dict(models.get("roles") or {})
        merged_roles.update(llm.get("roles") or {})  # finops.yaml overrides models.yaml
        cfg.llm = LlmConfig(
            provider=llm.get("provider", cfg.llm.provider),
            region=llm.get("region", cfg.llm.region),
            roles=merged_roles,
            fallback=list(llm.get("fallback") or models.get("fallback") or []),
            temperature=float(llm.get("temperature", models.get("temperature", cfg.llm.temperature))),
            max_tokens=int(llm.get("max_tokens", models.get("max_tokens", cfg.llm.max_tokens))),
            cache_prompt=bool(llm.get("cache_prompt", models.get("cache_prompt", cfg.llm.cache_prompt))),
            cache_tools=bool(llm.get("cache_tools", models.get("cache_tools", cfg.llm.cache_tools))),
            guardrail_id=llm.get("guardrail_id", cfg.llm.guardrail_id),
            guardrail_version=str(llm.get("guardrail_version", cfg.llm.guardrail_version)),
            guardrail_trace=llm.get("guardrail_trace", cfg.llm.guardrail_trace),
        )

        g = data.get("guardrails") or {}
        cfg.guardrails = GuardrailsConfig(
            athena_max_scanned_gb=int(
                g.get("athena_max_scanned_gb", cfg.guardrails.athena_max_scanned_gb)
            ),
            require_confirmation=bool(
                g.get("require_confirmation", cfg.guardrails.require_confirmation)
            ),
            redact_account_ids=bool(
                g.get("redact_account_ids", cfg.guardrails.redact_account_ids)
            ),
        )

        t = data.get("telemetry") or {}
        cfg.telemetry = TelemetryConfig(
            enabled=bool(t.get("enabled", cfg.telemetry.enabled)),
            exporter=t.get("exporter", cfg.telemetry.exporter),
            endpoint=t.get("endpoint", cfg.telemetry.endpoint),
            protocol=t.get("protocol", cfg.telemetry.protocol),
            service_name=t.get("service_name", cfg.telemetry.service_name),
            sample_ratio=float(t.get("sample_ratio", cfg.telemetry.sample_ratio)),
            traces=bool(t.get("traces", cfg.telemetry.traces)),
            metrics=bool(t.get("metrics", cfg.telemetry.metrics)),
            logs=bool(t.get("logs", cfg.telemetry.logs)),
            content=t.get("content", cfg.telemetry.content),
        )

        cfg._apply_env_overrides()
        return cfg

    def _apply_env_overrides(self) -> None:
        self.mode = os.getenv("FINOPS_MODE", self.mode)
        self.skills_enabled = _env_bool("FINOPS_SKILLS", self.skills_enabled)

        self.aws.auth = os.getenv("FINOPS_AWS_AUTH", self.aws.auth)
        self.aws.profile = _first_env("FINOPS_AWS_PROFILE", "AWS_PROFILE") or self.aws.profile
        self.aws.region = (
            _first_env("FINOPS_AWS_REGION", "AWS_REGION", "AWS_DEFAULT_REGION") or self.aws.region
        )
        self.aws.ce_region = os.getenv("FINOPS_CE_REGION", self.aws.ce_region)
        self.aws.org_mode = _env_bool("FINOPS_ORG_MODE", self.aws.org_mode)
        self.aws.assume_base = os.getenv("FINOPS_ASSUME_BASE", self.aws.assume_base)
        self.aws.role_arn = os.getenv("FINOPS_ROLE_ARN", self.aws.role_arn)
        self.aws.external_id = os.getenv("FINOPS_EXTERNAL_ID", self.aws.external_id)

        self.llm.provider = os.getenv("FINOPS_LLM_PROVIDER", self.llm.provider)
        self.llm.region = os.getenv("FINOPS_LLM_REGION", self.llm.region)
        if os.getenv("FINOPS_LLM_TEMPERATURE"):
            self.llm.temperature = float(os.environ["FINOPS_LLM_TEMPERATURE"])
        if os.getenv("FINOPS_LLM_MAX_TOKENS"):
            self.llm.max_tokens = int(os.environ["FINOPS_LLM_MAX_TOKENS"])
        self.llm.cache_prompt = _env_bool("FINOPS_LLM_CACHE", self.llm.cache_prompt)
        self.llm.cache_tools = _env_bool("FINOPS_LLM_CACHE", self.llm.cache_tools)
        self.llm.guardrail_id = os.getenv("FINOPS_GUARDRAIL_ID", self.llm.guardrail_id)
        self.llm.guardrail_version = os.getenv("FINOPS_GUARDRAIL_VERSION", self.llm.guardrail_version)
        self.llm.guardrail_trace = os.getenv("FINOPS_GUARDRAIL_TRACE", self.llm.guardrail_trace)
        for role in ("orchestrator", "cost", "optimization", "sql", "digest"):
            override = os.getenv(f"FINOPS_MODEL_{role.upper()}")
            if override:
                self.llm.roles[role] = override

        self.guardrails.redact_account_ids = _env_bool(
            "FINOPS_REDACT_ACCOUNT_IDS", self.guardrails.redact_account_ids
        )

        self.telemetry.enabled = _env_bool("FINOPS_TELEMETRY", self.telemetry.enabled)
        self.telemetry.exporter = os.getenv("FINOPS_TELEMETRY_EXPORTER", self.telemetry.exporter)
        # FINOPS_TELEMETRY_ENDPOINT wins; else honor the standard OTEL env so OTLP "just works".
        self.telemetry.endpoint = _first_env(
            "FINOPS_TELEMETRY_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"
        ) or self.telemetry.endpoint
        self.telemetry.protocol = os.getenv("FINOPS_TELEMETRY_PROTOCOL", self.telemetry.protocol)
        self.telemetry.service_name = os.getenv(
            "FINOPS_TELEMETRY_SERVICE", self.telemetry.service_name
        )
        if os.getenv("FINOPS_TELEMETRY_SAMPLE_RATIO"):
            self.telemetry.sample_ratio = float(os.environ["FINOPS_TELEMETRY_SAMPLE_RATIO"])
        self.telemetry.content = os.getenv("FINOPS_TELEMETRY_CONTENT", self.telemetry.content)

    # ---- helpers -------------------------------------------------------
    def redacted(self) -> dict:
        """Config snapshot safe to print/log (no secrets; ARN account id masked)."""
        return {
            "mode": self.mode,
            "aws": {
                "auth": self.aws.auth,
                "profile": self.aws.profile if self.aws.auth != "env" else None,
                "region": self.aws.region,
                "ce_region": self.aws.ce_region,
                "org_mode": self.aws.org_mode,
                "assume_base": self.aws.assume_base if self.aws.auth == "assume_role" else None,
                "role_arn": _mask_arn(self.aws.role_arn),
            },
            "llm": {
                "provider": self.llm.provider,
                "region": self.llm.region,
                "roles": self.llm.roles,
                "fallback": self.llm.fallback,
            },
            "guardrails": vars(self.guardrails),
            "telemetry": {
                "enabled": self.telemetry.enabled,
                "exporter": self.telemetry.exporter,
                "endpoint": self.telemetry.endpoint,
                "protocol": self.telemetry.protocol,
                "sample_ratio": self.telemetry.sample_ratio,
                "content": self.telemetry.content,
                "signals": {
                    "traces": self.telemetry.traces,
                    "metrics": self.telemetry.metrics,
                    "logs": self.telemetry.logs,
                },
            },
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "skills_enabled": self.skills_enabled,
        }
