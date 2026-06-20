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
