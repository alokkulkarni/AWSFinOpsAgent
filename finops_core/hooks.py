"""Strands hooks for steering agent behavior at the tool layer.

- ReadOnlyGuard: cancels any write-shaped tool unless the mode permits it (defense-in-depth on
  top of the UI/API mode gating — the LLM can never mutate AWS in advisory/artifacts mode).
- ToolMeter: counts tool invocations for observability/audit.

`strands` is imported here, so import this module only where the agent extra is installed
(it's used inside the build_*_agent factories).
"""
from __future__ import annotations

from typing import Optional

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry

from finops_core.config import Config
from finops_core.modes import tool_blocked


def _tool_name(event) -> str:
    return (getattr(event, "tool_use", None) or {}).get("name", "")


class ReadOnlyGuard(HookProvider):
    """Block write-shaped tools unless mode == guarded_write."""

    def __init__(self, mode: str):
        self.mode = mode

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self._guard)

    def _guard(self, event: BeforeToolCallEvent) -> None:
        name = _tool_name(event)
        if tool_blocked(name, self.mode):
            event.cancel_tool = (
                f"blocked by ReadOnlyGuard: '{name}' requires guarded_write "
                f"(current mode: {self.mode})"
            )


class ToolMeter(HookProvider):
    """Count tool calls per agent run (audit + observability)."""

    def __init__(self):
        self.calls: dict[str, int] = {}

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(AfterToolCallEvent, self._count)

    def _count(self, event: AfterToolCallEvent) -> None:
        name = _tool_name(event) or "?"
        self.calls[name] = self.calls.get(name, 0) + 1

    def summary(self) -> dict:
        return {"tool_calls": sum(self.calls.values()), "by_tool": dict(self.calls)}


def default_hooks(cfg: Optional[Config] = None, meter: Optional[ToolMeter] = None) -> list:
    """ReadOnlyGuard for the config's mode, plus an optional ToolMeter."""
    cfg = cfg or Config.load()
    hooks: list = [ReadOnlyGuard(cfg.mode)]
    if meter is not None:
        hooks.append(meter)
    return hooks
