"""A local, file-backed Strands ``MemoryStore`` — persistent agent memory with no infra.

Entries are stored as a JSON list (``[{"content": str, "metadata": dict|null}, ...]``) under a
per-agent namespace file. Search is keyword/token-overlap relevance (no embeddings → nothing to
provision, no per-query cost) which is plenty for recalling a handful of durable "important
aspects" and validating them against new prompts.

Implements only ``add`` (+ ``search``): a writable store that exposes ``add`` but not
``add_messages`` makes Strands default to a client-side ``ModelExtractor`` for automatic
extraction (it distills salient facts via the model and writes each through ``add``) — exactly the
behavior we want. See ``finops_core.memory.attach_memory``.

Secrets hygiene (CLAUDE.md): 12-digit AWS account IDs are redacted on write by default, and the
default store path lives outside the repo (``~/.finops_agent/memory``). Recalled memory is treated
as *data*, never instructions (consistent with the prompt-injection posture in SPEC §14).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from finops_core.memory import redact_account_ids, score_overlap


class LocalJSONMemoryStore:
    """File-backed memory store satisfying the Strands ``MemoryStore`` protocol (duck-typed)."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        path,
        max_search_results: int = 5,
        writable: bool = True,
        extraction: Any = False,
        redact: bool = True,
    ):
        self.name = name
        self.description = description
        self.max_search_results = max_search_results
        self.writable = writable
        self.extraction = extraction          # bool | ExtractionConfig — read by MemoryManager
        self._redact = redact
        self._path = Path(path)

    # --- persistence (no IO at construction; created lazily on first write) --
    def _load(self) -> list[dict]:
        if not self._path.is_file():
            return []
        try:
            data = json.loads(self._path.read_text() or "[]")
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save(self, entries: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False))
        os.replace(tmp, self._path)  # atomic swap

    def _clean(self, value):
        return redact_account_ids(value) if (self._redact and isinstance(value, str)) else value

    # --- MemoryStore protocol -----------------------------------------------
    async def add(self, content: str, metadata: Optional[dict] = None) -> Any:
        """Persist one fact. Redacts account IDs (when enabled) and dedupes identical content."""
        content = self._clean(content)
        if metadata:
            metadata = {k: self._clean(v) for k, v in metadata.items()}
        entries = self._load()
        if any(e.get("content") == content for e in entries):
            return content  # dedupe: at-least-once extraction must tolerate repeats
        entries.append({"content": content, "metadata": metadata})
        self._save(entries)
        return content

    async def search(self, query: str, options: Any = None) -> list:
        """Return the most relevant entries (token overlap), newest first on ties."""
        from strands.memory import MemoryEntry  # lazy: only needed on the agent path

        entries = self._load()
        if not entries:
            return []
        limit = self.max_search_results
        if options is not None:
            limit = (options.get("max_search_results") if isinstance(options, dict)
                     else getattr(options, "max_search_results", None)) or limit

        scored = [
            (score_overlap(query, e.get("content", "")), idx, e)
            for idx, e in enumerate(entries)
        ]
        # score desc, then most-recently-added first (higher original index) on ties
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        hits = [e for s, _idx, e in scored if s > 0][:limit]
        return [
            MemoryEntry(content=e["content"], store_name=self.name, metadata=e.get("metadata"))
            for e in hits
        ]
