from __future__ import annotations

import time
import discord
from discord import app_commands
from discord.ext import commands


def _mod_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    ch = discord.utils.get(guild.text_channels, name="mod-logs")
    return ch if isinstance(ch, discord.TextChannel) else None


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.command(name="warn", description="Warn a member (logged as a case).")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        cid = await self.bot.cases_store.add(interaction.guild.id, member.id, interaction.user.id, "warn", reason, int(time.time()))  # type: ignore[attr-defined]

        try:
            await member.send(f"You were warned in **{interaction.guild.name}**. Case #{cid}. Reason: {reason or '—'}")
        except discord.HTTPException:
            pass

        ch = _mod_log_channel(interaction.guild)
        if ch:
            e = discord.Embed(title="Warn", description=f"Case #{cid}")
            e.add_field(name="Member", value=f"{member} ({member.id})", inline=False)
            e.add_field(name="Actor", value=f"{interaction.user} ({interaction.user.id})", inline=False)
            e.add_field(name="Reason", value=reason or "—", inline=False)
            await ch.send(embed=e)

        await interaction.followup.send(f"✅ Warned. Case #{cid}.", ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout a member (logged as a case).")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 10080], reason: str | None = None) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        until = discord.utils.utcnow() + discord.timedelta(minutes=int(minutes))
        await member.timeout(until, reason=reason)
        cid = await self.bot.cases_store.add(interaction.guild.id, member.id, interaction.user.id, "timeout", reason, int(time.time()))  # type: ignore[attr-defined]

        ch = _mod_log_channel(interaction.guild)
        if ch:
            e = discord.Embed(title="Timeout", description=f"Case #{cid}")
            e.add_field(name="Member", value=f"{member} ({member.id})", inline=False)
            e.add_field(name="Duration", value=f"{minutes} minutes", inline=False)
            e.add_field(name="Reason", value=reason or "—", inline=False)
            await ch.send(embed=e)

        await interaction.followup.send(f"✅ Timed out. Case #{cid}.", ephemeral=True)

    @app_commands.command(name="purge", description="Bulk delete messages in a channel.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 200]) -> None:
        assert interaction.channel is not None
        await interaction.response.defer(ephemeral=True)
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.followup.send("❌ Not a text channel.", ephemeral=True)
            return
        deleted = await interaction.channel.purge(limit=int(count))
        await interaction.followup.send(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)

    @app_commands.command(name="cases", description="Show recent cases for a member.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def cases(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        rows = await self.bot.cases_store.list_for_user(interaction.guild.id, member.id, limit=10)  # type: ignore[attr-defined]
        if not rows:
            await interaction.followup.send("No cases.", ephemeral=True)
            return
        e = discord.Embed(title=f"Cases: {member}")
        for c in rows:
            e.add_field(name=f"#{c.case_id} • {c.action}", value=(c.reason or "—")[:250], inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)
