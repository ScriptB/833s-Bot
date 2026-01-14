from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..permissions import require_verified


class UtilitiesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.command(name="avatar", description="Show a user's avatar.")
    @require_verified()
    async def avatar(self, interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        target = user or interaction.user  # type: ignore[assignment]
        embed = discord.Embed(title=f"{target.display_name}'s avatar")
        embed.set_image(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="userinfo", description="Show basic user info.")
    @require_verified()
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        assert interaction.guild is not None
        m = user or interaction.user  # type: ignore[assignment]
        roles = [r.mention for r in getattr(m, "roles", []) if r.name != "@everyone"][-12:]
        embed = discord.Embed(title=f"User: {m}")
        embed.add_field(name="ID", value=str(m.id), inline=True)
        embed.add_field(name="Created", value=str(m.created_at)[:19], inline=True)
        if hasattr(m, "joined_at") and m.joined_at:
            embed.add_field(name="Joined", value=str(m.joined_at)[:19], inline=True)
        embed.add_field(name="Roles", value=(" ".join(roles) if roles else "None"), inline=False)
        embed.set_thumbnail(url=m.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="serverinfo", description="Show basic server info.")
    @require_verified()
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        g = interaction.guild
        embed = discord.Embed(title=f"Server: {g.name}")
        embed.add_field(name="ID", value=str(g.id), inline=True)
        embed.add_field(name="Members", value=str(g.member_count or 0), inline=True)
        embed.add_field(name="Owner", value=str(g.owner) if g.owner else "Unknown", inline=True)
        embed.add_field(name="Created", value=str(g.created_at)[:19], inline=True)
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)
