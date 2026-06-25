"""Conversation management — the context-rot fix.

Long-lived agents (the dashboard chat panels reuse a cached ``Agent`` across every turn; the
A2A agent servers hold one ``Agent`` for the process lifetime) otherwise re-send the full raw
transcript to Bedrock on every turn → rising cost/latency and an eventual context-window
overflow that crashes the turn.

``build_conversation_manager`` returns a Strands ``SummarizingConversationManager`` that, instead
of *dropping* old turns (the default ``SlidingWindowConversationManager``), folds the oldest
history into a compact running summary and keeps the most recent turns verbatim. It runs *inside*
the event loop — proactively via a ``BeforeModelCall`` threshold hook, and reactively on overflow
— so it is automatic and never interrupts the conversation.

Mirrors ``finops_core/hooks.py``: ``strands`` is imported lazily so this module is importable
without the agent extra; the agent factories call it the same way they call ``default_hooks``.
"""
from __future__ import annotations

from typing import Optional

from finops_core.config import Config

# The summary is conversational context, never the source of displayed figures (those always come
# from the deterministic tool layer — numbers-must-be-exact). The prompt is explicit about
# preserving, not estimating, any number it does carry forward.
FINOPS_SUMMARY_PROMPT = (
    "You are summarizing an AWS FinOps / DevOps assistant conversation so it can continue without "
    "the full transcript. Produce a concise third-person summary that PRESERVES, verbatim and "
    "EXACT: every dollar figure, percentage, and date/time period; every service, resource, "
    "account, region, and tag identifier mentioned; the user's goals, constraints, and decisions; "
    "and any open follow-ups. Never invent, round, or estimate a number — copy figures exactly as "
    "they appeared. Omit chit-chat and redundant tool chatter. Output only the summary."
)


def build_conversation_manager(cfg: Optional[Config] = None, router=None, *, enabled: Optional[bool] = None):
    """Return a configured ``SummarizingConversationManager``, or ``None`` when disabled.

    ``None`` lets the agent factory omit the ``conversation_manager`` kwarg entirely, so Strands
    falls back to its default sliding-window manager (the prior behavior) — a clean off switch.

    enabled: tri-state gate (per-call override). ``None`` → use ``cfg.conversation.summarize``;
             ``True``/``False`` force on/off (the CLI ``--summarize/--no-summarize`` flag).
    router: optional ``ModelRouter``; only used when ``cfg.conversation.summarizer_role`` selects a
            (typically cheaper) model to do the summarizing. Defaults to the agent's own model.
    """
    cfg = cfg or Config.load()
    conv = cfg.conversation
    active = conv.summarize if enabled is None else enabled
    if not active:
        return None

    from strands.agent.conversation_manager import (  # lazy: requires the agent extra
        ProactiveCompressionConfig,
        SummarizingConversationManager,
    )

    proactive = (
        ProactiveCompressionConfig(compression_threshold=conv.proactive_threshold)
        if conv.proactive_threshold and conv.proactive_threshold > 0
        else None
    )

    summarization_agent = _summarizer_agent(conv.summarizer_role, router)

    return SummarizingConversationManager(
        summary_ratio=conv.summary_ratio,
        preserve_recent_messages=conv.preserve_recent,
        summarization_system_prompt=FINOPS_SUMMARY_PROMPT,
        summarization_agent=summarization_agent,
        proactive_compression=proactive,
    )


def _summarizer_agent(role: Optional[str], router):
    """A lightweight, tool-less agent on a (cheap) model used only to write summaries.

    Returns ``None`` (→ summarize with the parent agent's own model) when no role is configured or
    the model can't be resolved — summarization must never break the main conversation.
    """
    if not role or router is None:
        return None
    try:
        from strands import Agent  # lazy: requires the agent extra

        return Agent(
            model=router.for_role(role),
            system_prompt=FINOPS_SUMMARY_PROMPT,
            callback_handler=None,
        )
    except Exception:  # pragma: no cover - defensive: fall back to the parent model
        return None
