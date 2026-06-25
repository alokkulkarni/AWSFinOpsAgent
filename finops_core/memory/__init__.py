"""Persistent, cross-session agent memory (Strands ``MemoryManager`` + a local store).

Gives the FinOps and DevOps agents durable recall of "important aspects": facts are captured
automatically (the model distills salient points each interval) *and* on demand (an explicit
"remember this" tool), then auto-injected into — and queryable against — future prompts.

Mirrors ``finops_core/skills`` and ``finops_core/conversation``:
- The pure-python helpers here import no ``strands`` (so the module is importable without the
  agent extra and is unit-testable directly): ``memory_active``, ``memory_path``,
  ``redact_account_ids``, ``score_overlap``.
- ``attach_memory`` lazy-imports ``strands`` + the store, and returns ``agent_kwargs`` the agent
  factories splat into ``Agent(...)`` — an identity no-op (``{}``) when disabled, exactly like
  ``attach_skills``.

Per-agent namespaces (``finops`` / ``devops``) keep each agent's memory separate, the same way
each agent has its own skills folder.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# 12-digit AWS account ids — reuse the same shape config.py masks ARNs with.
_ACCOUNT_RE = re.compile(r"\d{12}")
_TOKEN_RE = re.compile(r"[a-z0-9]+")

FINOPS_NS = "finops"
DEVOPS_NS = "devops"


# --- pure helpers (no strands) ---------------------------------------------
def redact_account_ids(text: str) -> str:
    """Mask any 12-digit AWS account id (secrets hygiene on memory writes)."""
    return _ACCOUNT_RE.sub("************", text)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def score_overlap(query: str, content: str) -> int:
    """Relevance = count of shared tokens between query and a stored entry (cheap, local)."""
    return len(_tokens(query) & _tokens(content))


def memory_active(cfg=None, override: Optional[bool] = None) -> bool:
    """Resolve whether memory is on: explicit ``override`` wins, else ``cfg.memory.enabled``."""
    if override is not None:
        return bool(override)
    mem = getattr(cfg, "memory", None)
    return bool(getattr(mem, "enabled", False))


def memory_path(cfg, namespace: str) -> Path:
    """The on-disk file for an agent's memory namespace (``~`` expanded)."""
    base = Path(getattr(cfg.memory, "dir", "~/.finops_agent/memory")).expanduser()
    return base / f"{namespace}.json"


# --- strands-backed wiring (lazy import) -----------------------------------
def attach_memory(cfg, namespace: str, *, enabled: bool, router=None) -> dict:
    """Return ``{"memory_manager": MemoryManager}`` when ``enabled``, else ``{}`` (no-op).

    The store implements ``add``+``search`` only, so enabling ``auto_extract`` makes Strands use a
    client-side ``ModelExtractor`` (distill → ``add``). ``allow_write_tool`` adds the explicit
    "remember" tool; injection (auto-recall) + a search tool are always on when memory is on.
    """
    if not enabled:
        return {}

    from strands.memory import MemoryManager  # lazy: requires the agent extra

    from finops_core.memory.store import LocalJSONMemoryStore

    redact = bool(getattr(cfg.guardrails, "redact_account_ids", True))
    extraction = _extraction_config(cfg, router) if cfg.memory.auto_extract else False

    store = LocalJSONMemoryStore(
        name=namespace,
        description=(
            f"Durable {namespace} memory: user goals, account/resource facts, prior decisions and "
            "preferences. Search it to recall or validate context before answering."
        ),
        path=memory_path(cfg, namespace),
        max_search_results=cfg.memory.max_search_results,
        extraction=extraction,
        redact=redact,
    )
    return {
        "memory_manager": MemoryManager(
            stores=[store],
            injection=True,                          # auto-recall into each prompt
            search_tool_config=True,                 # agent can query/validate memory
            add_tool_config=bool(cfg.memory.allow_write_tool),  # explicit "remember this"
        )
    }


def _extraction_config(cfg, router):
    """An ``ExtractionConfig`` that distills facts with a (cheap) model, or ``True`` for defaults.

    When a router is available we pin extraction to the configured/cheap ``summarizer``/``digest``
    model so per-interval distillation stays inexpensive; otherwise ``True`` lets Strands default
    to a ``ModelExtractor`` on the agent's own model.
    """
    if router is None:
        return True
    try:
        from strands.memory import ExtractionConfig, ModelExtractor

        role = getattr(cfg.conversation, "summarizer_role", None) or "digest"
        return ExtractionConfig(
            extractor=ModelExtractor(
                model=router.for_role(role),
                system_prompt=(
                    "Extract durable, reusable facts from this AWS FinOps/DevOps conversation: "
                    "user goals, account/resource/region identifiers, preferences, and decisions. "
                    "Copy any figures exactly. One terse fact per line; skip transient chatter."
                ),
            )
        )
    except Exception:  # pragma: no cover - defensive: fall back to default extraction
        return True
