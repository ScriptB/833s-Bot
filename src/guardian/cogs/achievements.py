from __future__ import annotations

import datetime as dt
import discord
from discord import app_commands
from discord.ext import commands


_ACH = {
    "daily_streak_7": ("Weekly Habit", "Claim daily for 7 days."),
    "daily_streak_14": ("Fortnight Habit", "Claim daily for 14 days."),
    "wallet_10k": ("Five Digits", "Reach 10,000 Credits."),
    "wallet_100k": ("Six Digits", "Reach 100,000 Credits."),
}


def _fmt_ts(ts: int) -> str:
    if ts <= 0:
        return "-"
    return dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


class AchievementsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.command(name="achievements", description="Show your unlocked achievements.")
    async def achievements(self, interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        target = user or interaction.user  # type: ignore[assignment]
        rows = await self.bot.achievements_store.list_user(interaction.guild.id, target.id)  # type: ignore[attr-defined]
        if not rows:
            await interaction.followup.send("No achievements yet.", ephemeral=True)
            return

        lines = []
        for code, ts, meta in rows[-25:]:
            name, desc = _ACH.get(code, (code, ""))
            lines.append(f"**{name}** — {desc} (`{_fmt_ts(ts)}`)")
        embed = discord.Embed(title=f"Achievements — {target.display_name}", description="\n".join(lines))
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="achievements_top", description="Leaderboard: most achievements.")
    async def achievements_top(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        rows = await self.bot.achievements_store.leaderboard(interaction.guild.id, limit=10)  # type: ignore[attr-defined]
        if not rows:
            await interaction.followup.send("No data yet.", ephemeral=True)
            return
        lines = []
        for i, (uid, cnt) in enumerate(rows, 1):
            member = interaction.guild.get_member(uid)
            name = member.display_name if member else f"<@{uid}>"
            lines.append(f"**{i}.** {name} — **{cnt}**")
        embed = discord.Embed(title="Top Achievements", description="\n".join(lines))
        await interaction.followup.send(embed=embed, ephemeral=True)
