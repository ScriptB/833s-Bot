from __future__ import annotations

import asyncio
from typing import Iterable

import discord
from discord import app_commands
from discord.ext import commands

from ..ui.overhaul_interactive import OverhaulInteractiveView
from ..utils import safe_embed, permission_overwrite, get_confirmation
from ..constants import DEFAULT_TIMEOUT_SECONDS, COLORS


class SetupAutoConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="overhaul",
        description="Interactive server rebuild with customizable options and real-time progress.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def overhaul(self, interaction: discord.Interaction) -> None:
        """Interactive server overhaul with customization UI."""
        assert interaction.guild is not None
        guild = interaction.guild

        # Permission check
        bot_member = guild.me or guild.get_member(self.bot.user.id)  # type: ignore[attr-defined]
        if not bot_member or not (bot_member.guild_permissions.manage_channels and bot_member.guild_permissions.manage_roles):
            await interaction.response.send_message("❌ Bot needs Manage Channels + Manage Roles permissions.", ephemeral=True)
            return

        # Create and show interactive view
        view = OverhaulInteractiveView(self, guild)
        embed = view._create_config_embed()
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()
