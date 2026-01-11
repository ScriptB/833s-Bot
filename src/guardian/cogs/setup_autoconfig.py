from __future__ import annotations

import asyncio
from typing import Iterable

import discord
from discord import app_commands
from discord.ext import commands

from ..ui.overhaul_interactive import OverhaulInteractiveView
from ..utils import safe_embed, permission_overwrite, get_confirmation
from ..constants import DEFAULT_TIMEOUT_SECONDS, COLORS
from ..security.auth import root_only


class SetupAutoConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.guild_only()
    @root_only()
    @app_commands.command(
        name="overhaul",
        description="Interactive server rebuild with customizable options and real-time progress. (Root only)",
    )
    @app_commands.describe(
        confirm="Type 'OVERHAUL_CONFIRM' to confirm this destructive action"
    )
    async def overhaul(self, interaction: discord.Interaction, confirm: str) -> None:
        """Interactive server overhaul with customization UI (Root only)."""
        assert interaction.guild is not None
        guild = interaction.guild

        # Safety rule: Must be in staff channel
        if not any(name.lower() in interaction.channel.name.lower() for name in ['staff', 'admin', 'moderator', 'command', 'bot-commands']):
            await interaction.response.send_message(
                "❌ This command can only be used in staff channels (staff, admin, moderator, command, bot-commands).",
                ephemeral=True
            )
            return

        # Safety rule: Confirmation required
        if confirm != "OVERHAUL_CONFIRM":
            await interaction.response.send_message(
                "❌ Confirmation required. Type exactly: `OVERHAUL_CONFIRM` to proceed with this destructive action.",
                ephemeral=True
            )
            return

        # Safety rule: Bot permissions check
        bot_member = guild.me or guild.get_member(self.bot.user.id)  # type: ignore[attr-defined]
        if not bot_member or not (bot_member.guild_permissions.manage_channels and bot_member.guild_permissions.manage_roles):
            await interaction.response.send_message("❌ Bot needs Manage Channels + Manage Roles permissions.", ephemeral=True)
            return

        # Safety rule: Create confirmation view
        class OverhaulConfirmationView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60.0)
                self.confirmed = False

            @discord.ui.button(label="⚠️ YES, Overhaul Server", style=discord.ButtonStyle.danger)
            async def confirm_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                self.confirmed = True
                button_interaction.response.send_message("✅ Overhaul confirmed. Starting...", ephemeral=True)
                self.stop()

            @discord.ui.button(label="❌ CANCEL", style=discord.ButtonStyle.secondary)
            async def cancel_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                button_interaction.response.send_message("❌ Overhaul cancelled.", ephemeral=True)
                self.stop()

        # Show confirmation dialog
        confirm_view = OverhaulConfirmationView()
        await interaction.response.send_message(
            "⚠️ **WARNING**: This will completely rebuild the server!\n\n"
            "This action will:\n"
            "• Delete all channels and categories\n"
            "• Delete all roles (except protected ones)\n"
            "• Recreate everything from scratch\n"
            "• **This cannot be undone!**\n\n"
            "Are you absolutely sure you want to continue?",
            view=confirm_view,
            ephemeral=True
        )

        # Wait for confirmation
        await confirm_view.wait()
        
        if not confirm_view.confirmed:
            return

        # Create and show interactive view
        view = OverhaulInteractiveView(self, guild)
        embed = view._create_config_embed()
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()
