from __future__ import annotations

import asyncio
from typing import Iterable

import discord
from discord import app_commands
from discord.ext import commands

from ..ui.overhaul_authoritative import AuthoritativeOverhaulExecutor
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
        description="Execute authoritative server rebuild with confirmation. (Root only)",
    )
    @app_commands.describe(
        confirm="Type 'OVERHAUL_CONFIRM' to confirm this destructive action"
    )
    async def overhaul(self, interaction: discord.Interaction, confirm: str) -> None:
        """Execute authoritative server overhaul with confirmation (Root only)."""
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
        if not bot_member or not (bot_member.guild_permissions.administrator):
            await interaction.response.send_message("❌ Bot needs Administrator permissions.", ephemeral=True)
            return

        # Show authoritative overhaul warning
        await interaction.response.send_message(
            "⚠️ **AUTHORITATIVE SERVER OVERHAUL CONFIRMATION**\n\n"
            "This will **DELETE ALL CHANNELS, CATEGORIES, AND ROLES** then recreate the server with:\n\n"
            "**✅ PROFESSIONAL STRUCTURE:**\n"
            "• Proper role hierarchy (Owner → Admin → Moderator → Support → Verified → Member)\n"
            "• Interest-gated categories (Coding Lab, Gaming, etc.)\n"
            "• Level-based reward system (Bronze → Silver → Gold → Platinum → Diamond)\n"
            "• Enforced permissions and access control\n"
            "• No duplicate or junk roles\n\n"
            "**❌ THIS ACTION IS IRREVERSIBLE**\n\n"
            "**Type `OVERHAUL_CONFIRM` to proceed:**",
            ephemeral=True
        )

        # Wait for confirmation
        try:
            def check(m: discord.Message) -> bool:
                return m.author == interaction.user and m.channel == interaction.channel and m.content.strip() == "OVERHAUL_CONFIRM"
            
            await self.bot.wait_for("message", check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Overhaul cancelled - confirmation timeout.", ephemeral=True)
            return

        # Execute authoritative overhaul
        await interaction.followup.send("✅ **Authoritative Overhaul started**\n\nExecuting professional server restructuring...", ephemeral=True)
