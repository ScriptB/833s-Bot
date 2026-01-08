from __future__ import annotations

import asyncio
import json
import random
import time
import discord
from discord import app_commands
from discord.ext import commands

from ..ui.giveaways import GiveawayView


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


class GiveawaysCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self._task: asyncio.Task | None = None

    async def cog_load(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="guardian-giveaways")

    async def cog_unload(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(10)
            now = int(time.time())
            due = await self.bot.giveaways_store.due(now)  # type: ignore[attr-defined]
            for guild_id, channel_id, message_id, ends_ts, winners, prize, entries_json in due:
                guild = self.bot.get_guild(int(guild_id))  # type: ignore[attr-defined]
                if not guild:
                    await self.bot.giveaways_store.mark_ended(int(guild_id), int(message_id))  # type: ignore[attr-defined]
                    continue
                channel = guild.get_channel(int(channel_id))
                if not isinstance(channel, discord.TextChannel):
                    await self.bot.giveaways_store.mark_ended(int(guild_id), int(message_id))  # type: ignore[attr-defined]
                    continue
                try:
                    msg = await channel.fetch_message(int(message_id))
                except discord.HTTPException:
                    await self.bot.giveaways_store.mark_ended(int(guild_id), int(message_id))  # type: ignore[attr-defined]
                    continue

                entries = [int(x) for x in json.loads(entries_json or "[]")]
                entries = list(dict.fromkeys(entries))
                chosen = []
                if entries:
                    chosen = random.sample(entries, k=min(int(winners), len(entries)))

                winners_text = ", ".join(f"<@{uid}>" for uid in chosen) if chosen else "No valid entries"
                embed = msg.embeds[0] if msg.embeds else discord.Embed()
                embed.title = "🎉 Giveaway Ended"
                embed.clear_fields()
                embed.add_field(name="Prize", value=str(prize), inline=False)
                embed.add_field(name="Winners", value=winners_text, inline=False)

                try:
                    await msg.edit(embed=embed, view=None)
                    await channel.send(f"🎉 Giveaway ended! Winners: {winners_text}")
                except discord.HTTPException:
                    pass

                await self.bot.giveaways_store.mark_ended(int(guild_id), int(message_id))  # type: ignore[attr-defined]

    @app_commands.command(name="giveaway_start", description="Start a giveaway. Duration: 10m, 2h, 1d.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_start(
        self,
        interaction: discord.Interaction,
        duration: str,
        prize: str,
        winners: app_commands.Range[int, 1, 20] = 1,
        channel: discord.TextChannel | None = None,
    ) -> None:
        assert interaction.guild is not None
        secs = _parse_duration(duration)
        if secs is None or secs <= 0:
            await interaction.response.send_message("❌ Invalid duration. Use 10m, 2h, 1d.", ephemeral=True)
            return

        channel = channel or interaction.channel  # type: ignore
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ Invalid channel.", ephemeral=True)
            return

        ends = int(time.time() + secs)
        embed = discord.Embed(title="🎁 Giveaway", description="Use the buttons to join/leave.")
        embed.add_field(name="Prize", value=prize, inline=False)
        embed.add_field(name="Ends", value=f"<t:{ends}:R>", inline=False)
        embed.add_field(name="Winners", value=str(int(winners)), inline=False)

        msg = await channel.send(embed=embed)
        view = GiveawayView(interaction.guild.id, msg.id)
        self.bot.add_view(view, message_id=msg.id)  # type: ignore[attr-defined]
        await msg.edit(view=view)

        await self.bot.giveaways_store.create(interaction.guild.id, channel.id, msg.id, ends, int(winners), prize)  # type: ignore[attr-defined]
        await interaction.response.send_message(f"✅ Giveaway started: {msg.jump_url}", ephemeral=True)
