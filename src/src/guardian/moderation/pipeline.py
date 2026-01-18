from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import discord

from ..services.moderation_audit_store import ModerationAuditStore
from ..services.moderation_config_store import ModerationConfigStore
from .models import ModDecision, ModEvent
from .rule_engine import CompiledRuleset, collapse_actions, compile_ruleset, evaluate_ruleset


def _now() -> datetime:
    return datetime.utcnow()


class RulesetCache:
    """Compiled ruleset cache per guild.

    Invalidated automatically when published revision changes.
    """

    def __init__(self) -> None:
        self._cache: dict[int, CompiledRuleset] = {}

    def get(self, guild_id: int) -> Optional[CompiledRuleset]:
        return self._cache.get(guild_id)

    def set(self, guild_id: int, ruleset: CompiledRuleset) -> None:
        self._cache[guild_id] = ruleset

    def invalidate(self, guild_id: int) -> None:
        self._cache.pop(guild_id, None)


class ModerationPipeline:
    def __init__(
        self,
        *,
        bot: discord.Client,
        config_store: ModerationConfigStore,
        audit_store: ModerationAuditStore,
        cache: RulesetCache,
    ) -> None:
        self.bot = bot
        self.config_store = config_store
        self.audit = audit_store
        self.cache = cache

    async def get_ruleset(self, guild_id: int) -> CompiledRuleset:
        published_rev, doc = await self.config_store.get_published(guild_id)
        cached = self.cache.get(guild_id)
        if cached and cached.revision == published_rev:
            return cached
        compiled = compile_ruleset(guild_id, published_rev, doc)
        self.cache.set(guild_id, compiled)
        return compiled

    async def decide(self, event: ModEvent, *, member_role_ids: Optional[list[int]] = None) -> ModDecision:
        ruleset = await self.get_ruleset(event.guild_id)
        correlation_id = str(uuid.uuid4())

        hits = evaluate_ruleset(ruleset, event, member_role_ids=member_role_ids)
        actions = collapse_actions(hits)

        # Audit ingress
        await self.audit.add(
            guild_id=event.guild_id,
            correlation_id=correlation_id,
            event_type=event.event_type,
            user_id=event.user_id,
            channel_id=event.channel_id,
            message_id=event.message_id,
            status="ingested",
            created_at_iso=_now().isoformat(timespec="seconds"),
            details={
                "hits": [
                    {
                        "rule_id": h.rule_id,
                        "priority": h.priority,
                        "reason": h.reason,
                        "actions": [a.action_type for a in h.actions],
                        "stop": h.stop,
                    }
                    for h in hits
                ],
            },
        )

        return ModDecision(correlation_id=correlation_id, event=event, hits=hits, actions=actions)
