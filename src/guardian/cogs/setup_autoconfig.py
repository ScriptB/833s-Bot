from __future__ import annotations

import asyncio
from typing import Iterable

import discord
from discord import app_commands
from discord.ext import commands

from ..ui.overhaul_setup import OverhaulSetupView


def _p(*, view: bool, send: bool, history: bool = True, reactions: bool = True, threads: bool = True) -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=view,
        send_messages=send,
        read_message_history=history,
        add_reactions=reactions,
        create_public_threads=threads,
        create_private_threads=threads,
        send_messages_in_threads=send,
    )


def _safe_embed(title: str, description: str) -> discord.Embed:
    # hard limit safety
    if len(description) > 4000:
        description = description[:3990] + "…"
    return discord.Embed(title=title, description=description)


class SetupAutoConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="guardian_overhaul",
        description="Interactive UI to fully delete all channels/roles and rebuild a clean, compact server with reaction roles.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def guardian_overhaul(self, interaction: discord.Interaction) -> None:
        """Interactive, configurable server overhaul."""
        assert interaction.guild is not None
        guild = interaction.guild

        await interaction.response.defer(ephemeral=True, thinking=True)

        bot_member = guild.me or guild.get_member(self.bot.user.id)  # type: ignore[attr-defined]
        if not bot_member:
            await interaction.followup.send("❌ Bot member not found.", ephemeral=True)
            return

        gperms = bot_member.guild_permissions
        if not (gperms.manage_channels and gperms.manage_roles):
            await interaction.followup.send("❌ Missing permissions: Manage Channels + Manage Roles.", ephemeral=True)
            return

        # Present the interactive configuration UI
        view = OverhaulSetupView(self, guild)
        embed = discord.Embed(
            title="🛠️ Server Overhaul Configuration",
            description="Use the buttons below to configure the overhaul. When ready, click **Execute Overhaul**. This will **DELETE ALL CHANNELS AND ROLES**, then rebuild from your configuration.",
        )
        embed.add_field(name="⚠️ Warning", value="This action is irreversible. Please back up anything important.", inline=False)
        msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        view.message = msg  # allow the view to edit itself later
