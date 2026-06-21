"""Render a .drawio to PNG/SVG/PDF via the draw.io desktop CLI when available.

Returns the output path, or None if the CLI isn't installed (callers then use the SVG fallback).
Per the drawio skill: `drawio -x -f <fmt> -e -b 10 -o <out> <in>`.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

_CANDIDATES = [
    "drawio",  # Linux PATH (snap/apt/flatpak) / headless container
    "/Applications/draw.io.app/Contents/MacOS/draw.io",  # macOS
    "/usr/bin/drawio",
]


def find_drawio_cli() -> Optional[str]:
    for c in _CANDIDATES:
        if c == "drawio":
            p = shutil.which("drawio")
            if p:
                return p
        elif Path(c).exists():
            return c
    return None


def render(drawio_path: str, fmt: str = "png", out: Optional[str] = None) -> Optional[str]:
    cli = find_drawio_cli()
    if not cli:
        return None
    out = out or f"{drawio_path}.{fmt}"
    cmd = [cli, "-x", "-f", fmt, "-e", "-b", "10", "-o", out, drawio_path]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return out if Path(out).exists() else None
    except Exception:
        return None
