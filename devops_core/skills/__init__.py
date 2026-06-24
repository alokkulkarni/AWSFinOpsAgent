"""DevOps agent skills — progressive-disclosure instruction packages for the estate agent.

The reusable machinery (discovery, gating, the scoped reader, ``attach_skills``) lives in
``finops_core.skills``; this package only holds the DevOps skill folder + its path constant,
mirroring how ``devops_core`` reuses the FinOps ``ModelRouter`` and hooks.
"""
from __future__ import annotations

from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parent
ESTATE_SKILLS_DIR = SKILLS_ROOT / "estate"
