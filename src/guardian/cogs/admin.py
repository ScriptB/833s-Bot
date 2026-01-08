from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..services.guild_store import GuildConfig


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="set_welcome_channel", description="Set the welcome channel for this server.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_welcome_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        assert interaction.guild is not None
        cfg = await self.bot.guild_store.get(interaction.guild.id)  # type: ignore[attr-defined]
        new_cfg = GuildConfig(
            guild_id=cfg.guild_id,
            welcome_channel_id=channel.id,
            autorole_id=cfg.autorole_id,
            log_channel_id=cfg.log_channel_id,
            anti_spam_max_msgs=cfg.anti_spam_max_msgs,
            anti_spam_window_seconds=cfg.anti_spam_window_seconds,
            anti_spam_timeout_seconds=cfg.anti_spam_timeout_seconds,
        )
        await self.bot.guild_store.upsert(new_cfg)  # type: ignore[attr-defined]
        await interaction.response.send_message(f"Welcome channel set to {channel.mention}", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.command(name="set_autorole", description="Set a role to automatically grant to new members.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def set_autorole(self, interaction: discord.Interaction, role: discord.Role) -> None:
        assert interaction.guild is not None
        cfg = await self.bot.guild_store.get(interaction.guild.id)  # type: ignore[attr-defined]
        new_cfg = GuildConfig(
            guild_id=cfg.guild_id,
            welcome_channel_id=cfg.welcome_channel_id,
            autorole_id=role.id,
            log_channel_id=cfg.log_channel_id,
            anti_spam_max_msgs=cfg.anti_spam_max_msgs,
            anti_spam_window_seconds=cfg.anti_spam_window_seconds,
            anti_spam_timeout_seconds=cfg.anti_spam_timeout_seconds,
        )
        await self.bot.guild_store.upsert(new_cfg)  # type: ignore[attr-defined]
        await interaction.response.send_message(f"Autorole set to {role.mention}", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="set_log_channel", description="Set a channel where the bot will post moderation logs.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        assert interaction.guild is not None
        cfg = await self.bot.guild_store.get(interaction.guild.id)  # type: ignore[attr-defined]
        new_cfg = GuildConfig(
            guild_id=cfg.guild_id,
            welcome_channel_id=cfg.welcome_channel_id,
            autorole_id=cfg.autorole_id,
            log_channel_id=channel.id,
            anti_spam_max_msgs=cfg.anti_spam_max_msgs,
            anti_spam_window_seconds=cfg.anti_spam_window_seconds,
            anti_spam_timeout_seconds=cfg.anti_spam_timeout_seconds,
        )
        await self.bot.guild_store.upsert(new_cfg)  # type: ignore[attr-defined]
        await interaction.response.send_message(f"Log channel set to {channel.mention}", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="set_antispam", description="Tune anti-spam thresholds for this server.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_antispam(
        self,
        interaction: discord.Interaction,
        max_messages: app_commands.Range[int, 3, 30],
        window_seconds: app_commands.Range[int, 2, 30],
        timeout_seconds: app_commands.Range[int, 5, 3600],
    ) -> None:
        assert interaction.guild is not None
        cfg = await self.bot.guild_store.get(interaction.guild.id)  # type: ignore[attr-defined]
        new_cfg = GuildConfig(
            guild_id=cfg.guild_id,
            welcome_channel_id=cfg.welcome_channel_id,
            autorole_id=cfg.autorole_id,
            log_channel_id=cfg.log_channel_id,
            anti_spam_max_msgs=int(max_messages),
            anti_spam_window_seconds=int(window_seconds),
            anti_spam_timeout_seconds=int(timeout_seconds),
        )
        await self.bot.guild_store.upsert(new_cfg)  # type: ignore[attr-defined]
        await interaction.response.send_message(
            f"Anti-spam updated: max **{max_messages}** msgs / **{window_seconds}s** -> timeout **{timeout_seconds}s**",
            ephemeral=True,
        )

    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="queue_status", description="Show queue size and pacing policy.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def queue_status(self, interaction: discord.Interaction) -> None:
        q = self.bot.task_queue  # type: ignore[attr-defined]
        s = self.bot.settings  # type: ignore[attr-defined]
        await interaction.response.send_message(
            f"Queue size: **{q.size()}**\n"
            f"Pacing: **{s.queue_max_batch}** tasks / **{s.queue_every_ms}ms** (max size {s.queue_max_size})",
            ephemeral=True,
        )

    @set_welcome_channel.error
    @set_autorole.error
    @set_log_channel.error
    @set_antispam.error
    @queue_status.error
    async def _on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("Missing permissions.", ephemeral=True)
            return
        raise error
