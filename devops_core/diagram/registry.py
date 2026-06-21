"""In-process hand-off for diagram-on-request: the `draw_diagram` tool records the rendered
artifact here; the dashboard reads it after the agent responds and renders it + download buttons.

The tool runs in the same process as the (local) dashboard agent, so a module-level slot is the
simplest reliable channel — the large SVG never round-trips through the LLM (token-conscious).
Thread-guarded for Streamlit's rerun model.
"""
from __future__ import annotations

import threading
from typing import Optional

_lock = threading.Lock()
_last: Optional[dict] = None


def record_diagram(artifact: dict) -> None:
    global _last
    with _lock:
        _last = artifact


def last_diagram() -> Optional[dict]:
    with _lock:
        return _last


def clear() -> None:
    global _last
    with _lock:
        _last = None
