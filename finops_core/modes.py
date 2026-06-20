"""Action-posture mode gating — one place that decides what each mode permits, used by the
CLI, API, dashboard, and the remediation engine.

  advisory      — read-only / advisory (default)
  artifacts     — advisory + generate fix scripts/IaC (never executed)
  guarded_write — artifacts + apply allowlisted, human-confirmed, audited actions
"""
from __future__ import annotations

MODES = ["advisory", "artifacts", "guarded_write"]

_ARTIFACT_MODES = {"artifacts", "guarded_write"}
_WRITE_MODES = {"guarded_write"}


def normalize_mode(mode) -> str:
    """Return a valid mode, defaulting to 'advisory' for anything unrecognized/None."""
    return mode if mode in MODES else "advisory"


def can_generate_artifacts(mode: str) -> bool:
    return mode in _ARTIFACT_MODES


def can_apply_actions(mode: str) -> bool:
    return mode in _WRITE_MODES


# Tool-name prefixes that indicate a mutating ("write") tool. Used by the ReadOnlyGuard hook
# as defense-in-depth — even if a write tool is ever attached to an agent, advisory/artifacts
# mode blocks it at call time.
WRITE_TOOL_PREFIXES = (
    "apply_", "create_", "delete_", "release_", "modify_",
    "enable_", "disable_", "provision_", "put_", "update_", "stop_",
)


def is_write_tool(name: str) -> bool:
    return bool(name) and name.lower().startswith(WRITE_TOOL_PREFIXES)


def tool_blocked(tool_name: str, mode: str) -> bool:
    """True if a write-shaped tool should be blocked in this mode."""
    return is_write_tool(tool_name) and not can_apply_actions(mode)
