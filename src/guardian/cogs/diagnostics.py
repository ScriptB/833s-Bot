# DiagnosticsCog temporarily disabled to reduce command count
# and avoid Discord's 100 command limit
# 
# Commands removed: ping, uptime, stats, config_show (4 commands)
# These can be re-enabled later when command count is optimized

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m {secs}s"
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


async def _safe_respond(interaction: discord.Interaction, content: str, *, ephemeral: bool = True) -> None:
    """Respond safely to an interaction.

    Avoids 404 Unknown interaction (code 10062) by acknowledging quickly and falling back to followups.
    """
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral, thinking=False)
        await interaction.followup.send(content, ephemeral=ephemeral)
    except discord.NotFound:
        # Interaction expired (common during deploy/restart or slow acknowledgement).
        return
    except discord.HTTPException:
        return


class DiagnosticsCog(commands.Cog):
    """Temporarily disabled diagnostics cog to reduce command count."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    # All diagnostic commands temporarily commented out
    # @app_commands.command(name="ping", description="Show bot latency.")
    # async def ping(self, interaction: discord.Interaction) -> None:
    #     latency_ms = int(self.bot.latency * 1000)  # type: ignore[attr-defined]
    #     await _safe_respond(interaction, f"🏓 Pong: **{latency_ms}ms**", ephemeral=True)

    # @app_commands.command(name="uptime", description="Show how long the bot has been running.")
    # async def uptime(self, interaction: discord.Interaction) -> None:
    #     stats = self.bot.stats  # type: ignore[attr-defined]
    #     await _safe_respond(interaction, f"⏱️ Uptime: **{_format_duration(stats.uptime_seconds())}**", ephemeral=True)

    # @app_commands.command(name="stats", description="Show queue and runtime stats.")
    # @app_commands.checks.has_permissions(manage_guild=True)
    # async def stats_cmd(self, interaction: discord.Interaction) -> None:
    #     q = self.bot.task_queue  # type: ignore[attr-defined]
    #     s = self.bot.stats  # type: ignore[attr-defined]
    #     msg = (
    #         f"📊 **833's Guardian Stats**\n"
    #         f"• Queue size: **{q.size()}**\n"
    #         f"• Tasks enqueued: **{s.tasks_enqueued}**\n"
    #         f"• Tasks executed: **{s.tasks_executed}**\n"
    #         f"• Tasks failed: **{s.tasks_failed}**\n"
    #         f"• Welcomes sent: **{s.welcomes_sent}**\n"
    #         f"• Roles assigned: **{s.roles_assigned}**\n"
    #         f"• Messages deleted: **{s.messages_deleted}**\n"
    #         f"• Timeouts applied: **{s.timeouts_applied}**\n"
    #     )
    #     await _safe_respond(interaction, msg, ephemeral=True)

    # @app_commands.command(name="config_show", description="Show the server configuration stored by the bot.")
    # @app_commands.checks.has_permissions(manage_guild=True)
    # async def config_show(self, interaction: discord.Interaction) -> None:
    #     assert interaction.guild is not None
    #     cfg = await self.bot.guild_store.get(interaction.guild.id)  # type: ignore[attr-defined]
    #     msg = (
    #         f"⚙️ **Server Config**\n"
    #         f"• Welcome channel: `{cfg.welcome_channel_id}`\n"
    #         f"• Autorole: `{cfg.autorole_id}`\n"
    #         f"• Log channel: `{cfg.log_channel_id}`\n"
    #         f"• Anti-spam: max `{cfg.anti_spam_max_msgs}` in `{cfg.anti_spam_window_seconds}s` → timeout `{cfg.anti_spam_timeout_seconds}s`"
    #     )
    #     await _safe_respond(interaction, msg, ephemeral=True)

    # @stats_cmd.error
    # @config_show.error
    # async def _on_perm_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    #     if isinstance(error, app_commands.MissingPermissions):
    #         await _safe_respond(interaction, "❌ Missing permissions.", ephemeral=True)
    #         return
    #     raise error
