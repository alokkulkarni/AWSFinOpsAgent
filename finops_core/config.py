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


@dataclass
class GuardrailsConfig:
    athena_max_scanned_gb: int = 10
    require_confirmation: bool = True
    redact_account_ids: bool = True


@dataclass
class Config:
    mode: str = "advisory"           # advisory | artifacts | guarded_write
    aws: AwsConfig = field(default_factory=AwsConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    guardrails: GuardrailsConfig = field(default_factory=GuardrailsConfig)
    cache_ttl_seconds: int = 3600

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

        cfg._apply_env_overrides()
        return cfg

    def _apply_env_overrides(self) -> None:
        self.mode = os.getenv("FINOPS_MODE", self.mode)

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
        for role in ("orchestrator", "cost", "optimization", "sql", "digest"):
            override = os.getenv(f"FINOPS_MODEL_{role.upper()}")
            if override:
                self.llm.roles[role] = override

        self.guardrails.redact_account_ids = _env_bool(
            "FINOPS_REDACT_ACCOUNT_IDS", self.guardrails.redact_account_ids
        )

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
            "cache_ttl_seconds": self.cache_ttl_seconds,
        }
