from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..ui.tickets import TicketCreateView


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.command(name="ticket_panel", description="Post a ticket panel in #tickets.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_panel(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)

        ch = discord.utils.get(interaction.guild.text_channels, name="tickets")
        if not ch:
            await interaction.followup.send("❌ Channel #tickets not found.", ephemeral=True)
            return

        view = TicketCreateView(self.bot, interaction.guild.id)
        self.bot.add_view(view)  # type: ignore[attr-defined]
        embed = discord.Embed(title="Support Tickets", description="Click to open a private ticket channel.")
        await ch.send(embed=embed, view=view)
        await interaction.followup.send("✅ Ticket panel posted.", ephemeral=True)
