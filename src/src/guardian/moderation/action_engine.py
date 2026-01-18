from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional

import discord

from ..services.moderation_audit_store import ModerationAuditStore
from ..services.moderation_idempotency_store import ModerationIdempotencyStore
from ..services.warnings_store import WarningsStore
from .models import ExecuteResult, ModAction, ModDecision


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _dedupe_key(decision: ModDecision, action: ModAction, index: int) -> str:
    # Stable per event + rule chain. Message ID is best; fallback to correlation + index.
    mid = decision.event.message_id or 0
    return f"{decision.correlation_id}:{mid}:{index}:{action.action_type}"


class ActionEngine:
    """Executes actions safely with idempotency + retries.

    Retries are bounded and only used for HTTPException/Timeouts.
    """

    def __init__(
        self,
        *,
        bot: discord.Client,
        audit_store: ModerationAuditStore,
        idempotency_store: ModerationIdempotencyStore,
        warnings_store: WarningsStore,
    ) -> None:
        self.bot = bot
        self.audit = audit_store
        self.idem = idempotency_store
        self.warnings = warnings_store

    async def execute(self, decision: ModDecision) -> ExecuteResult:
        attempted = 0
        executed = 0
        skipped = 0
        failed = 0
        errors: list[str] = []

        guild = self.bot.get_guild(decision.event.guild_id)
        if guild is None:
            return ExecuteResult(decision.correlation_id, ok=False, attempted=0, executed=0, skipped_idempotent=0, failed=0, errors=["guild_not_found"])

        member = guild.get_member(decision.event.user_id)

        for idx, action in enumerate(decision.actions):
            attempted += 1
            dkey = _dedupe_key(decision, action, idx)
            if not await self.idem.claim(guild.id, dkey, _now_iso()):
                skipped += 1
                continue

            try:
                await self._execute_one(guild, member, decision, action)
                executed += 1
            except Exception as e:
                failed += 1
                errors.append(f"{action.action_type}:{type(e).__name__}:{e}")
                await self.audit.add(
                    guild_id=guild.id,
                    correlation_id=decision.correlation_id,
                    event_type=decision.event.event_type,
                    user_id=decision.event.user_id,
                    channel_id=decision.event.channel_id,
                    message_id=decision.event.message_id,
                    status="action_failed",
                    created_at_iso=_now_iso(),
                    action_type=action.action_type,
                    details={"error": repr(e), "params": action.params},
                )

        return ExecuteResult(
            correlation_id=decision.correlation_id,
            ok=failed == 0,
            attempted=attempted,
            executed=executed,
            skipped_idempotent=skipped,
            failed=failed,
            errors=errors,
        )

    async def _execute_one(
        self,
        guild: discord.Guild,
        member: Optional[discord.Member],
        decision: ModDecision,
        action: ModAction,
    ) -> None:
        # Backoff wrapper for discord API calls
        async def _retry(coro_fn, *, tries: int = 3):
            last = None
            for t in range(tries):
                try:
                    return await coro_fn()
                except (discord.HTTPException, asyncio.TimeoutError) as e:
                    last = e
                    await asyncio.sleep(0.5 * (2**t))
            raise last  # type: ignore

        at = action.action_type
        params = action.params or {}
        now_iso = _now_iso()

        if at == "delete_message":
            if decision.event.channel_id and decision.event.message_id:
                ch = guild.get_channel(decision.event.channel_id)
                if isinstance(ch, (discord.TextChannel, discord.Thread)):
                    async def _do():
                        msg = await ch.fetch_message(decision.event.message_id)  # may 404
                        await msg.delete(reason="AutoMod")

                    await _retry(_do)

        elif at == "warn":
            reason = str(params.get("reason") or "AutoMod")
            await self.warnings.add_warning(guild.id, decision.event.user_id, self.bot.user.id if self.bot.user else 0, reason, now_iso)
            await self.audit.add(
                guild_id=guild.id,
                correlation_id=decision.correlation_id,
                event_type=decision.event.event_type,
                user_id=decision.event.user_id,
                channel_id=decision.event.channel_id,
                message_id=decision.event.message_id,
                status="warned",
                created_at_iso=now_iso,
                action_type="warn",
                details={"reason": reason},
            )

        elif at == "timeout":
            if member is None:
                return
            minutes = int(params.get("minutes") or 10)
            until = datetime.utcnow() + timedelta(minutes=minutes)
            async def _do():
                await member.timeout(until, reason="AutoMod")
            await _retry(_do)
            await self.audit.add(
                guild_id=guild.id,
                correlation_id=decision.correlation_id,
                event_type=decision.event.event_type,
                user_id=decision.event.user_id,
                channel_id=decision.event.channel_id,
                message_id=decision.event.message_id,
                status="timed_out",
                created_at_iso=now_iso,
                action_type="timeout",
                details={"minutes": minutes},
            )

        elif at == "kick":
            if member is None:
                return
            async def _do():
                await member.kick(reason="AutoMod")
            await _retry(_do)

        elif at == "ban":
            user = member or discord.Object(id=decision.event.user_id)
            async def _do():
                await guild.ban(user, reason="AutoMod", delete_message_days=0)
            await _retry(_do)

        elif at == "notify_dm":
            if member is None:
                return
            text = str(params.get("text") or "A moderation action was applied.")
            async def _do():
                await member.send(text)
            try:
                await _retry(_do, tries=2)
            except Exception:
                # Ignore DM failures
                pass

        elif at == "notify_channel":
            ch_id = params.get("channel_id")
            text = str(params.get("text") or "")
            if ch_id and text:
                ch = guild.get_channel(int(ch_id))
                if isinstance(ch, discord.TextChannel):
                    async def _do():
                        await ch.send(text)
                    await _retry(_do)

        elif at == "slowmode":
            ch_id = params.get("channel_id") or decision.event.channel_id
            seconds = int(params.get("seconds") or 10)
            ch = guild.get_channel(int(ch_id)) if ch_id else None
            if isinstance(ch, discord.TextChannel):
                async def _do():
                    await ch.edit(slowmode_delay=seconds, reason="AutoMod")
                await _retry(_do)

        elif at == "lock_channel":
            ch_id = params.get("channel_id") or decision.event.channel_id
            ch = guild.get_channel(int(ch_id)) if ch_id else None
            if isinstance(ch, discord.TextChannel):
                everyone = guild.default_role
                overwrite = ch.overwrites_for(everyone)
                overwrite.send_messages = False
                async def _do():
                    await ch.set_permissions(everyone, overwrite=overwrite, reason="AutoMod lockdown")
                await _retry(_do)

        elif at == "quarantine":
            if member is None:
                return
            rid = params.get("role_id")
            if rid:
                role = guild.get_role(int(rid))
                if role:
                    async def _do():
                        await member.add_roles(role, reason="AutoMod quarantine")
                    await _retry(_do)

        else:
            # Unknown actions are ignored for backward compatibility.
            return
