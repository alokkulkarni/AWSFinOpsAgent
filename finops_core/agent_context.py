"""Shared wiring for an agent's context lifecycle — conversation summarization + persistent
memory — folded into the ``Agent(...)`` kwargs.

One helper keeps the five agent build sites (cost/optimize/anomaly/estate factories + the inline
orchestrator) from drifting. Returns a dict the factory splats alongside ``**skill_kwargs``;
an empty/partial dict when a capability is off, so default-off paths stay byte-for-byte unchanged.
Mirrors the ``attach_skills`` ``(…, agent_kwargs)`` convention.
"""
from __future__ import annotations

from typing import Optional

from finops_core.config import Config


def agent_context_kwargs(
    cfg: Optional[Config] = None,
    namespace: str = "finops",
    *,
    router=None,
    conversation: Optional[bool] = None,
    memory: Optional[bool] = None,
) -> dict:
    """Build ``{conversation_manager?, memory_manager?}`` for ``Agent(...)``.

    conversation / memory: tri-state per-call overrides (``None`` → the config default, which is ON
    for both). ``namespace`` scopes the memory store per agent (``"finops"`` / ``"devops"``).
    """
    cfg = cfg or Config.load()

    from finops_core.conversation import build_conversation_manager
    from finops_core.memory import attach_memory, memory_active

    out: dict = {}
    cm = build_conversation_manager(cfg, router, enabled=conversation)
    if cm is not None:
        out["conversation_manager"] = cm
    out.update(attach_memory(cfg, namespace, enabled=memory_active(cfg, memory), router=router))
    return out
