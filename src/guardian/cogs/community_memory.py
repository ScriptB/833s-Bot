from __future__ import annotations

import datetime
import time
import discord
from discord import app_commands
from discord.ext import commands


class CommunityMemoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    community = app_commands.Group(name="community_memory", description="Community history and memory.")

    @community.command(name="timeline", description="Show recent community activity recorded by the bot.")
    async def timeline(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10] = 5) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        items = await self.bot.community_memory_store.latest(interaction.guild.id, int(limit))  # type: ignore[attr-defined]
        if not items:
            await interaction.followup.send("No community memory yet.", ephemeral=True)
            return
        lines = []
        for it in items:
            ts = datetime.datetime.utcfromtimestamp(it.ts).strftime("%Y-%m-%d %H:%M UTC")
            lines.append(f"{ts} • {it.kind}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @community.command(name="on_this_day", description="Show memory entries that happened on this day in previous years.")
    async def on_this_day(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10] = 5) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        now = datetime.datetime.utcnow()
        items = await self.bot.community_memory_store.on_this_day(interaction.guild.id, now.month, now.day, int(limit))  # type: ignore[attr-defined]
        if not items:
            await interaction.followup.send("No entries for this day.", ephemeral=True)
            return
        lines = []
        for it in items:
            ts = datetime.datetime.utcfromtimestamp(it.ts).strftime("%Y-%m-%d")
            lines.append(f"{ts} • {it.kind}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.community)
