"""Agent Skills — progressive-disclosure instruction packages (Strands ``AgentSkills`` plugin).

Mirrors ``finops_core/steering``: a skill is a versioned directory (``SKILL.md`` + optional
``references/``/``scripts/``) living under a per-agent folder here (and in
``devops_core/skills``). Only each skill's name + description are front-loaded into the system
prompt; the full instructions are pulled on demand when the model invokes the ``skills`` tool.

Design notes (kept deliberately like the rest of the codebase):
- The pure-python helpers (discovery, config gating, the scoped reader's path guard) import no
  ``strands`` so this module stays importable without the agent extra — the agent factories
  import these at module top, exactly as they do ``Config``/``ModelRouter``.
- The plugin and tool factories lazy-import ``strands`` (like ``build_*_agent`` and
  ``ModelRouter.for_role``), so nothing here pulls Bedrock/agent deps at import time.
- Skills are **instructions, never data**: exact figures must still come from the tool layer
  (numbers-must-be-exact). See SPEC.md §5.4.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# Per-agent skill folders (each a *parent* dir of skill directories; AgentSkills discovers the
# children with a SKILL.md). Scoping per agent keeps the reader's reach minimal — the cost agent
# cannot read the optimize agent's skill files.
SKILLS_ROOT = Path(__file__).resolve().parent
COST_SKILLS_DIR = SKILLS_ROOT / "cost"
OPTIMIZE_SKILLS_DIR = SKILLS_ROOT / "optimize"
ANOMALY_SKILLS_DIR = SKILLS_ROOT / "anomaly"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# --- pure-python discovery (no strands) ------------------------------------
def skill_metadata(skill_dir) -> dict:
    """Parse a skill's ``SKILL.md`` YAML frontmatter → ``{'name', 'description'}``.

    A tiny line parser (no PyYAML dependency, matching ``config.py``'s optional-yaml stance):
    top-level ``key: value`` lines only; nested/list lines (``metadata:`` children) are ignored.
    Raises ``ValueError`` if the frontmatter block is missing.
    """
    path = Path(skill_dir) / "SKILL.md"
    text = path.read_text()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(f"{path}: missing YAML frontmatter")
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return {"name": meta.get("name", ""), "description": meta.get("description", "")}


def list_skills(root) -> list[dict]:
    """Discover skills under ``root`` — each immediate child dir that has a ``SKILL.md``.

    Returns ``[{'name', 'description', 'dir'}]``. Lenient like the Strands loader: a child whose
    ``SKILL.md`` can't be parsed is skipped rather than aborting its siblings. Validation that a
    skill's name matches its directory is asserted in tests (the Agent Skills spec rule).
    """
    root = Path(root)
    if not root.is_dir():
        return []
    out: list[dict] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / "SKILL.md").is_file():
            continue
        try:
            meta = skill_metadata(child)
        except (OSError, ValueError):
            continue
        out.append({**meta, "dir": child})
    return out


def has_skills(root) -> bool:
    """True if ``root`` contains at least one discoverable skill."""
    return bool(list_skills(root))


def skills_active(cfg=None, override: Optional[bool] = None) -> bool:
    """Resolve whether skills are on: explicit ``override`` wins, else ``cfg.skills_enabled``
    (default ``False`` → existing agents are unchanged until a user opts in)."""
    if override is not None:
        return bool(override)
    return bool(getattr(cfg, "skills_enabled", False))


def read_under_root(root, path) -> str:
    """Read a file under ``root``, rejecting any path that resolves outside it.

    The path-escape guard behind ``build_skills_file_reader``'s tool, kept pure so it can be
    tested directly. Accepts an absolute path inside ``root`` (the location shown in the skill
    listing) or a path relative to ``root``.
    """
    root_resolved = Path(root).resolve()
    p = Path(path)
    target = (p if p.is_absolute() else root_resolved / p).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError(f"path escapes skills directory: {path}")
    if not target.is_file():
        raise FileNotFoundError(str(path))
    return target.read_text()


# --- strands-backed factories (lazy import) --------------------------------
def build_agent_skills(root, *, strict: bool = True):
    """Construct the Strands ``AgentSkills`` plugin for the skills under ``root``.

    Returns ``None`` when ``root`` has no skills so callers can treat skills as a no-op.
    ``strict=True`` surfaces a malformed ``SKILL.md`` instead of silently skipping it.
    """
    if not has_skills(root):
        return None
    from strands import AgentSkills  # lazy: requires the agent extra

    return AgentSkills(skills=str(Path(root)), strict=strict)


def build_skills_file_reader(root):
    """A ``@tool`` that reads a skill's bundled reference/script files, scoped to ``root``.

    This is the *only* filesystem reach skills add to an agent, and it is least-privilege:
    paths resolving outside ``root`` are rejected (see ``read_under_root``).
    """
    from strands import tool  # lazy: requires the agent extra

    @tool
    def read_skill_file(path: str) -> str:
        """Read a reference or script file bundled with an activated skill.

        ``path`` is the location shown in the activated skill's resource listing (absolute) or a
        path relative to the skills directory. Files outside the skills directory are rejected.
        """
        return read_under_root(root, path)

    return read_skill_file


def attach_skills(tools, root, *, enabled: bool, strict: bool = True):
    """Return ``(tools, agent_kwargs)`` augmented with the ``AgentSkills`` plugin + scoped reader
    when ``enabled`` and skills exist under ``root``.

    Identity no-op when disabled or when there are no skills — the agent factories pass the
    returned ``agent_kwargs`` straight to ``Agent(...)``, so default-off behavior is byte-for-byte
    the prior behavior (no ``plugins`` kwarg, no extra tool).
    """
    if not enabled:
        return tools, {}
    plugin = build_agent_skills(root, strict=strict)
    if plugin is None:
        return tools, {}
    return list(tools) + [build_skills_file_reader(root)], {"plugins": [plugin]}
