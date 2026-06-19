"""ModelRouter: resolves a model per agent role and verifies Bedrock availability.

`for_role()` lazily imports Strands so Phase-0 preflight runs without the agent extras.
`preflight()` uses the boto3 Bedrock control plane (read-only) to confirm the configured
inference-profile IDs exist in the region. Actual invoke access still requires model access
to be enabled in the Bedrock console.
"""
from __future__ import annotations

from dataclasses import dataclass

import boto3

from finops_core.aws.session import client
from finops_core.config import Config


@dataclass
class ModelPreflight:
    provider: str
    region: str
    reachable: bool
    resolved: dict          # role -> {"id": str, "available": True|False|None}
    notes: list


class ModelRouter:
    def __init__(self, cfg: Config, session: boto3.Session | None = None):
        self.cfg = cfg
        self.session = session
        self._roles = cfg.llm.roles or {}

    def model_id(self, role: str) -> str:
        rid = self._roles.get(role) or self._roles.get("orchestrator")
        if not rid:
            raise ValueError(f"no model configured for role {role!r}; set config/models.yaml")
        return rid

    def for_role(self, role: str):
        """Return a Strands model object for `role` (lazy import of strands).

        Temperature defaults to 0 so the agents relay tool figures deterministically.
        """
        temperature = self.cfg.llm.temperature
        if self.cfg.llm.provider == "anthropic":
            from strands.models.anthropic import AnthropicModel  # type: ignore
            return AnthropicModel(model_id=self.model_id(role), temperature=temperature)
        from strands.models import BedrockModel  # type: ignore
        return BedrockModel(
            model_id=self.model_id(role),
            region_name=self.cfg.llm.region,
            temperature=temperature,
        )

    def preflight(self) -> ModelPreflight:
        notes: list[str] = []
        resolved: dict = {}

        if self.cfg.llm.provider != "bedrock":
            return ModelPreflight(
                self.cfg.llm.provider,
                self.cfg.llm.region,
                True,
                {r: {"id": i, "available": None} for r, i in self._roles.items()},
                ["non-bedrock provider; skipped Bedrock control-plane checks"],
            )

        available_ids: set[str] = set()
        reachable = False
        try:
            bedrock = client(self.session, "bedrock", region=self.cfg.llm.region)
            try:
                paginator = bedrock.get_paginator("list_inference_profiles")
                for page in paginator.paginate():
                    for p in page.get("inferenceProfileSummaries", []):
                        available_ids.add(p.get("inferenceProfileId"))
            except Exception:
                for p in bedrock.list_inference_profiles().get("inferenceProfileSummaries", []):
                    available_ids.add(p.get("inferenceProfileId"))
            for m in bedrock.list_foundation_models().get("modelSummaries", []):
                available_ids.add(m.get("modelId"))
            reachable = True
        except Exception as e:  # control plane unreachable / no permission
            notes.append(f"could not reach Bedrock control plane: {e}")

        for role, rid in self._roles.items():
            resolved[role] = {"id": rid, "available": (rid in available_ids) if reachable else None}

        if reachable and any(v["available"] is False for v in resolved.values()):
            notes.append(
                "Some model IDs were not found in this region. Enable model access in the "
                "Bedrock console and/or fix the IDs in config/models.yaml."
            )
        return ModelPreflight(
            self.cfg.llm.provider, self.cfg.llm.region, reachable, resolved, notes
        )
