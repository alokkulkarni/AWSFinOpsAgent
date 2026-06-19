"""Append-only audit log + a file-based single-use confirmation-token store.

The token store lets `preview` (which mints a token) and `apply` (which consumes it) work across
separate CLI invocations and API requests. Both files live under audit/ (git-ignored).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_AUDIT_DIR = Path("audit")
_AUDIT_LOG = _AUDIT_DIR / "audit.jsonl"
_PENDING = _AUDIT_DIR / "pending.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_pending() -> dict:
    if _PENDING.exists():
        try:
            return json.loads(_PENDING.read_text())
        except Exception:
            return {}
    return {}


def _write_pending(data: dict) -> None:
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    _PENDING.write_text(json.dumps(data, indent=2))


def mint_token(action_id: str, params: dict, token: str) -> None:
    pending = _read_pending()
    pending[token] = {"action_id": action_id, "params": params, "created": _now()}
    _write_pending(pending)


def consume_token(token: str, action_id: str) -> Optional[dict]:
    """Return the stored params if the token is valid for this action, then remove it. Single use."""
    pending = _read_pending()
    entry = pending.pop(token, None)
    if not entry or entry.get("action_id") != action_id:
        return None
    _write_pending(pending)
    return entry.get("params", {})


def record(action_id: str, params: dict, status: str, detail: str, before=None, after=None) -> str:
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    ts = _now()
    audit_id = f"{ts}::{action_id}"
    entry = {"audit_id": audit_id, "ts": ts, "action_id": action_id, "params": params,
             "status": status, "detail": detail, "before": before, "after": after}
    with _AUDIT_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return audit_id
