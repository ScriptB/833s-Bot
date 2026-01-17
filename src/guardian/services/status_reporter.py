from __future__ import annotations

import time
from dataclasses import dataclass

import discord

from ..utils.lookup import find_text_channel


@dataclass
class StatusState:
    run_id: str
    started_at: int
    step: int
    total: int
    phase: str


class StatusReporter:
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        self._message_id_by_guild: dict[int, int] = {}
        self._state_by_guild: dict[int, StatusState] = {}

    async def start(self, guild: discord.Guild, total: int, phase: str) -> None:
        run_id = str(int(time.time()))
        self._state_by_guild[guild.id] = StatusState(run_id=run_id, started_at=int(time.time()), step=0, total=int(total), phase=phase)
        await self._ensure_message(guild)
        await self.update(guild, 0, phase)

    async def update(self, guild: discord.Guild, step: int, phase: str) -> None:
        st = self._state_by_guild.get(guild.id)
        if not st:
            return
        st.step = int(step)
        st.phase = str(phase)
        self._state_by_guild[guild.id] = st

        msg = await self._get_message(guild)
        if not msg:
            return

        e = discord.Embed(title="833s Guardian • Live Status")
        e.add_field(name="Phase", value=st.phase, inline=False)
        e.add_field(name="Progress", value=f"{st.step}/{st.total}", inline=True)
        e.add_field(name="Run ID", value=st.run_id, inline=True)
        e.set_footer(text="Updates live during rebuild/overhaul")
        try:
            await msg.edit(embed=e, content=None)
        except discord.HTTPException:
            return

        try:
            await self.bot.change_presence(activity=discord.Game(name=f"{st.phase} ({st.step}/{st.total})"))
        except Exception:
            pass

    async def finish(self, guild: discord.Guild, ok: bool, detail: str) -> None:
        st = self._state_by_guild.get(guild.id)
        if not st:
            return
        msg = await self._get_message(guild)
        if msg:
            e = discord.Embed(title="833s Guardian • Live Status")
            e.add_field(name="Result", value="✅ Complete" if ok else "❌ Failed", inline=False)
            e.add_field(name="Detail", value=(detail or "—")[:900], inline=False)
            e.add_field(name="Run ID", value=st.run_id, inline=True)
            try:
                await msg.edit(embed=e, content=None)
            except discord.HTTPException:
                pass
        try:
            await self.bot.change_presence(activity=discord.Game(name="Online • /help_commands"))
        except Exception:
            pass

    async def _ensure_message(self, guild: discord.Guild) -> None:
        ch = find_text_channel(guild, "bot-ops") or find_text_channel(guild, "admin-console") or find_text_channel(guild, "mod-logs")
        if not isinstance(ch, discord.TextChannel):
            return
        mid = self._message_id_by_guild.get(guild.id)
        if mid:
            return
        try:
            m = await ch.send("Initializing status…")
            self._message_id_by_guild[guild.id] = m.id
            try:
                await m.pin(reason="Live status")
            except discord.HTTPException:
                pass
        except discord.HTTPException:
            return

    async def _get_message(self, guild: discord.Guild) -> discord.Message | None:
        ch = find_text_channel(guild, "bot-ops") or find_text_channel(guild, "admin-console") or find_text_channel(guild, "mod-logs")
        if not isinstance(ch, discord.TextChannel):
            return None
        mid = self._message_id_by_guild.get(guild.id)
        if not mid:
            await self._ensure_message(guild)
            mid = self._message_id_by_guild.get(guild.id)
        if not mid:
            return None
        try:
            return await ch.fetch_message(mid)
        except discord.HTTPException:
            # recreate if missing
            self._message_id_by_guild.pop(guild.id, None)
            await self._ensure_message(guild)
            mid = self._message_id_by_guild.get(guild.id)
            if not mid:
                return None
            try:
                return await ch.fetch_message(mid)
            except discord.HTTPException:
                return None
