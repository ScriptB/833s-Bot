from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..ui.tickets import TicketCreateView
from ..permissions import require_staff


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self._view_registered = False

    async def cog_load(self) -> None:
        if not self._view_registered:
            self._view_registered = True
            try:
                # Register persistent view for all guilds
                self.bot.add_view(TicketCreateView(self.bot, 0))
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Re-attach persistent ticket views on bot startup."""
        for guild in self.bot.guilds:
            try:
                # Find existing ticket panel messages
                tickets_channel = discord.utils.get(guild.text_channels, name="tickets")
                if tickets_channel:
                    async for message in tickets_channel.history(limit=10):
                        if "Ticket Panel" in (message.embeds[0].title if message.embeds else ""):
                            # Re-attach view to existing ticket panel
                            self.bot.add_view(TicketCreateView(self.bot, guild.id), message_id=message.id)
                            break
            except Exception:
                continue

    @app_commands.command(name="ticket_panel", description="Post a ticket panel in #tickets.")
    @require_staff()
    async def ticket_panel(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        ch = discord.utils.get(interaction.guild.text_channels, name="tickets")
        if not ch:
            await interaction.followup.send("❌ Channel #tickets not found.", ephemeral=True)
            return

        view = TicketCreateView(self.bot, interaction.guild.id)
        embed = discord.Embed(title="Ticket Panel", description="Click to open a private ticket channel.")

        existing: discord.Message | None = None
        try:
            async for m in ch.history(limit=25):
                if not m.author or not getattr(self.bot, "user", None) or m.author.id != self.bot.user.id:
                    continue
                if not m.embeds:
                    continue
                if (m.embeds[0].title or "") == "Ticket Panel":
                    existing = m
                    break
        except Exception:
            existing = None

        try:
            if existing:
                self.bot.add_view(view, message_id=existing.id)
                await existing.edit(embed=embed, view=view)
                await interaction.followup.send("✅ Ticket panel updated.", ephemeral=True)
            else:
                msg = await ch.send(embed=embed, view=view)
                self.bot.add_view(view, message_id=msg.id)
                await interaction.followup.send("✅ Ticket panel posted.", ephemeral=True)
        except discord.HTTPException:
            await interaction.followup.send("❌ Failed to post the ticket panel.", ephemeral=True)
