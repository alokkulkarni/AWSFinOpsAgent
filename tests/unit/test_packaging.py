"""Guard that runtime data files (steering playbooks + agent skills) are declared in
``[tool.setuptools.package-data]`` so they ship in a non-editable wheel.

These files are loaded at runtime via ``Path(__file__)`` and are NOT importable code, so a
missing glob silently omits them from a wheel and the agent loads zero skills. The check mirrors
setuptools' recursive-``**`` glob semantics with the stdlib ``glob`` (verified to agree with a real
``pip wheel`` build); it stays fast and needs no build/network.
"""
import glob as _glob
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _package_data() -> dict:
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    return data["tool"]["setuptools"]["package-data"]


def _covered(pkg: str, rel: str) -> bool:
    """True if any package-data glob declared for ``pkg`` matches ``REPO/pkg/rel``."""
    pkg_dir = REPO / pkg
    target = (pkg_dir / rel).resolve()
    for pattern in _package_data().get(pkg, []):
        matches = {Path(p).resolve() for p in _glob.glob(str(pkg_dir / pattern), recursive=True)}
        if target in matches:
            return True
    return False


# Representative files that MUST land in the wheel (one per agent's skills + both steering sets).
REQUIRED = [
    ("finops_core", "steering/cost.md"),
    ("finops_core", "skills/cost/cost-drilldown-playbook/SKILL.md"),
    ("finops_core", "skills/optimize/savings-plan-vs-ri/SKILL.md"),
    ("finops_core", "skills/optimize/savings-plan-vs-ri/references/breakeven.md"),
    ("finops_core", "skills/anomaly/anomaly-triage/SKILL.md"),
    ("devops_core", "steering/devops.md"),
    ("devops_core", "skills/estate/incident-triage-runbook/SKILL.md"),
]


@pytest.mark.parametrize("pkg,rel", REQUIRED)
def test_required_data_file_is_packaged(pkg, rel):
    assert (REPO / pkg / rel).is_file(), f"missing on disk: {pkg}/{rel}"
    assert _covered(pkg, rel), f"{pkg}/{rel} is not matched by [tool.setuptools.package-data]"


def test_every_skill_markdown_is_packaged():
    """Any .md under a package's skills/ tree must be covered — so a newly added skill in an
    unexpected layout fails here instead of silently vanishing from the wheel."""
    on_disk = []
    for pkg in ("finops_core", "devops_core"):
        skills = REPO / pkg / "skills"
        if skills.is_dir():
            on_disk += [(pkg, p.relative_to(REPO / pkg).as_posix())
                        for p in skills.rglob("*.md") if p.is_file()]
    assert on_disk, "no skill .md files found — did the skills tree move?"
    missing = [f"{pkg}/{rel}" for pkg, rel in on_disk if not _covered(pkg, rel)]
    assert not missing, f"skill data files not covered by package-data: {missing}"
