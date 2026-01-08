from __future__ import annotations
import random
import discord
from discord import app_commands
from discord.ext import commands

class LevelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldowns = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        now = message.created_at.timestamp()
        last = self.cooldowns.get(message.author.id, 0)
        if now - last < 60:
            return
        self.cooldowns[message.author.id] = now
        xp = random.randint(10, 20)
        _, level, up = await self.bot.levels_store.add_xp(message.guild.id, message.author.id, xp)
        if up:
            await message.channel.send(f"🎉 {message.author.mention} reached level **{level}**!")

    @app_commands.command(name="rank", description="Show your rank")
    async def rank(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        xp, level = await self.bot.levels_store.get(interaction.guild.id, member.id)
        await interaction.response.send_message(
            f"⭐ {member.display_name}: Level **{level}**, XP **{xp}**",
            ephemeral=True,
        )

    @app_commands.command(name="leaderboard", description="XP leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await self.bot.levels_store.leaderboard(interaction.guild.id)
        if not rows:
            await interaction.response.send_message("No data yet.", ephemeral=True)
            return
        lines = []
        for i, (uid, lvl, xp) in enumerate(rows, start=1):
            m = interaction.guild.get_member(uid)
            name = m.display_name if m else str(uid)
            lines.append(f"{i}. {name} — L{lvl} ({xp} XP)")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
