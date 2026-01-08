from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class ReputationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.command(name="rep", description="Give +1 rep to a member (12h cooldown).")
    async def rep(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        if member.id == interaction.user.id:
            await interaction.followup.send("❌ Self rep not allowed.", ephemeral=True)
            return
        ok, val = await self.bot.reputation_store.give(interaction.guild.id, interaction.user.id, member.id, +1)  # type: ignore[attr-defined]
        if not ok:
            await interaction.followup.send(f"⏳ Cooldown remaining: {val}s", ephemeral=True)
            return
        await interaction.followup.send(f"✅ Rep given. {member.mention} now has **{val}** rep.", ephemeral=True)

    @app_commands.command(name="rep_show", description="Show a member's reputation.")
    async def rep_show(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        m = member or interaction.user
        score, _ = await self.bot.reputation_store.get(interaction.guild.id, m.id)  # type: ignore[attr-defined]
        await interaction.followup.send(f"**{m}** rep: **{score}**", ephemeral=True)
