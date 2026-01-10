from __future__ import annotations

import datetime
import time
import discord
from discord import app_commands
from discord.ext import commands


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    event = app_commands.Group(name="community_event", description="Community events (no pings).")

    async def _level(self, guild_id: int, user_id: int) -> int:
        _, _, lvl = await self.bot.levels_store.get(guild_id, user_id)  # type: ignore[attr-defined]
        return int(lvl)

    @event.command(name="create", description="Create an event (level 4+).")
    async def create(
        self,
        interaction: discord.Interaction,
        title: str,
        start_in_minutes: app_commands.Range[int, 1, 10080],
        description: str = "",
    ) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        if await self._level(interaction.guild.id, interaction.user.id) < 4:
            await interaction.followup.send("Requires level 4.", ephemeral=True)
            return
        # Hard cap active events to avoid clutter.
        active = await self.bot.events_store.active_count(interaction.guild.id)  # type: ignore[attr-defined]
        if active >= 25:
            await interaction.followup.send("Event limit reached.", ephemeral=True)
            return
        now = int(time.time())
        start_ts = now + int(start_in_minutes) * 60
        channel_id = interaction.channel_id or 0
        try:
            eid = await self.bot.events_store.create_event(  # type: ignore[attr-defined]
                interaction.guild.id,
                interaction.user.id,
                title=title,
                description=description,
                start_ts=start_ts,
                channel_id=int(channel_id),
            )
            try:
                await self.bot.community_memory_store.add(interaction.guild.id, "event_create", {"user_id": interaction.user.id, "event_id": eid})  # type: ignore[attr-defined]
            except Exception:
                pass
            await interaction.followup.send(f"Event created (ID {eid}).", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Title required.", ephemeral=True)

    @event.command(name="list", description="List upcoming active events.")
    async def list_events(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10] = 5) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        events = await self.bot.events_store.list_active(interaction.guild.id, int(limit))  # type: ignore[attr-defined]
        if not events:
            await interaction.followup.send("No active events.", ephemeral=True)
            return
        lines = []
        for e in events:
            ts = datetime.datetime.utcfromtimestamp(e.start_ts).strftime("%Y-%m-%d %H:%M UTC")
            lines.append(f"#{e.event_id} • {ts} • {e.title}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @event.command(name="info", description="Show event details.")
    async def info(self, interaction: discord.Interaction, event_id: int) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        e = await self.bot.events_store.get(interaction.guild.id, int(event_id))  # type: ignore[attr-defined]
        if not e or not e.active:
            await interaction.followup.send("Event not found.", ephemeral=True)
            return
        count = await self.bot.events_store.participants_count(interaction.guild.id, e.event_id)  # type: ignore[attr-defined]
        emb = discord.Embed(title=f"Event #{e.event_id}: {e.title}", description=e.description or "")
        emb.add_field(name="Starts", value=f"<t:{e.start_ts}:F>", inline=True)
        emb.add_field(name="Participants", value=str(count), inline=True)
        await interaction.followup.send(embed=emb, ephemeral=True)

    @event.command(name="join", description="Join an event.")
    async def join(self, interaction: discord.Interaction, event_id: int) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        e = await self.bot.events_store.get(interaction.guild.id, int(event_id))  # type: ignore[attr-defined]
        if not e or not e.active:
            await interaction.followup.send("Event not found.", ephemeral=True)
            return
        ok = await self.bot.events_store.join(interaction.guild.id, e.event_id, interaction.user.id)  # type: ignore[attr-defined]
        await interaction.followup.send("Joined." if ok else "Already joined.", ephemeral=True)

    @event.command(name="leave", description="Leave an event.")
    async def leave(self, interaction: discord.Interaction, event_id: int) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok = await self.bot.events_store.leave(interaction.guild.id, int(event_id), interaction.user.id)  # type: ignore[attr-defined]
        await interaction.followup.send("Left." if ok else "Not in event.", ephemeral=True)

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.event)
