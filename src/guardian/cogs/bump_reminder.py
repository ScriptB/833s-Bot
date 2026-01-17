from __future__ import annotations

import asyncio
import logging
import random

import discord
from discord.ext import commands

from ..utils import find_text_channel_fuzzy

log = logging.getLogger("guardian.bump_reminder")


class BumpReminderCog(commands.Cog):
    """Randomized bump reminders.

    Picks a random non-bot member and pings them with a configured message.
    The interval is randomized between min and max minutes.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._task: asyncio.Task | None = None
        self._ready_once = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._ready_once:
            return
        self._ready_once = True
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._runner())
            log.info("BumpReminderCog runner started")

    async def cog_unload(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def _runner(self) -> None:
        # Small initial delay to avoid racing other startup tasks
        await asyncio.sleep(10)
        while not self.bot.is_closed():
            try:
                await self._tick_all_guilds()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.exception("Bump reminder tick failed: %s", exc)

            settings = getattr(self.bot, "settings", None)
            min_m = int(getattr(settings, "bump_reminder_min_minutes", 20))
            max_m = int(getattr(settings, "bump_reminder_max_minutes", 120))
            if max_m < min_m:
                min_m, max_m = max_m, min_m
            delay = random.randint(min_m * 60, max_m * 60)
            await asyncio.sleep(delay)

    async def _tick_all_guilds(self) -> None:
        settings = getattr(self.bot, "settings", None)
        channel_name = getattr(settings, "bump_reminder_channel_name", "general-chat")
        base_message = getattr(
            settings,
            "bump_reminder_message",
            "Hey! Don't forget to use '!d Bump' to help the server grow!",
        )

        for guild in list(self.bot.guilds):
            try:
                ch = find_text_channel_fuzzy(guild, channel_name)
                if not isinstance(ch, discord.TextChannel):
                    continue

                member = await self._pick_random_member(guild)
                if not member:
                    continue

                msg = f"{member.mention} {base_message}".strip()
                await ch.send(msg)
            except discord.Forbidden:
                continue
            except discord.HTTPException:
                continue

    async def _pick_random_member(self, guild: discord.Guild) -> discord.Member | None:
        # Prefer cached members when available, otherwise fetch.
        members = [m for m in guild.members if not m.bot]
        if not members:
            try:
                members = [m async for m in guild.fetch_members(limit=None) if not m.bot]
            except discord.Forbidden:
                return None
            except discord.HTTPException:
                return None
        if not members:
            return None
        return random.choice(members)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BumpReminderCog(bot))
