from __future__ import annotations

import asyncio
import time
import logging
import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("guardian.cogs.reminders")


def _parse_duration(s: str) -> int | None:
    s = (s or "").strip().lower()
    try:
        num = int(s[:-1])
        unit = s[-1]
    except Exception:
        return None
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit)
    if not mult:
        return None
    return num * mult


class RemindersCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self._task: asyncio.Task | None = None

    async def cog_load(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="guardian-reminders")

    async def cog_unload(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(15)
                now = int(time.time())
                due = await self.bot.reminders_store.due(now)  # type: ignore[attr-defined]
                for rid, user_id, channel_id, guild_id, due_ts, msg in due:
                    try:
                        channel = self.bot.get_channel(int(channel_id))  # type: ignore[attr-defined]
                        if channel:
                            await channel.send(f"⏰ <@{user_id}> Reminder: {msg}")
                    except Exception:
                        pass
                    try:
                        await self.bot.reminders_store.delete(int(rid))  # type: ignore[attr-defined]
                    except Exception:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Reminders loop iteration failed")

    @app_commands.command(name="remind", description="Set a reminder. Duration: 10m, 2h, 1d, 30s.")
    async def remind(self, interaction: discord.Interaction, duration: str, message: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        secs = _parse_duration(duration)
        if secs is None or secs <= 0:
            await interaction.followup.send("❌ Invalid duration. Use 10m, 2h, 1d, 30s.", ephemeral=True)
            return
        due = int(time.time() + secs)
        rid = await self.bot.reminders_store.add(interaction.user.id, interaction.channel_id, interaction.guild_id, due, message)  # type: ignore[attr-defined]
        await interaction.followup.send(f"✅ Reminder set (ID `{rid}`) in {duration}.", ephemeral=True)
