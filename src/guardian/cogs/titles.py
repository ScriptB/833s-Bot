from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


TITLE_CATALOG: list[tuple[int, str]] = [
    (0, "New Face"),
    (2, "Regular"),
    (5, "Core"),
    (8, "Veteran"),
    (12, "Legend"),
]


class TitlesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    title = app_commands.Group(name="cosmetic_title", description="Cosmetic titles (no permissions).")

    async def _level(self, guild_id: int, user_id: int) -> int:
        _, _, lvl = await self.bot.levels_store.get(guild_id, user_id)  # type: ignore[attr-defined]
        return int(lvl)

    def _unlocked(self, lvl: int) -> list[str]:
        return [t for min_lvl, t in TITLE_CATALOG if lvl >= min_lvl]

    @title.command(name="list", description="List titles you can equip.")
    async def list_titles(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        lvl = await self._level(interaction.guild.id, interaction.user.id)
        unlocked = self._unlocked(lvl)
        current = await self.bot.titles_store.get(interaction.guild.id, interaction.user.id)  # type: ignore[attr-defined]
        lines = []
        for t in unlocked:
            mark = " (equipped)" if current.equipped == t else ""
            lines.append(f"- {t}{mark}")
        if not lines:
            lines = ["No titles available yet."]
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @title.command(name="equip", description="Equip a title you have unlocked.")
    async def equip(self, interaction: discord.Interaction, title: str) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        title = (title or "").strip()
        lvl = await self._level(interaction.guild.id, interaction.user.id)
        unlocked = self._unlocked(lvl)
        if title not in unlocked:
            await interaction.followup.send("Title not unlocked.", ephemeral=True)
            return
        await self.bot.titles_store.set_equipped(interaction.guild.id, interaction.user.id, title)  # type: ignore[attr-defined]
        try:
            await self.bot.community_memory_store.add(interaction.guild.id, "title_equipped", {"user_id": interaction.user.id, "title": title})  # type: ignore[attr-defined]
        except Exception:
            pass
        await interaction.followup.send("Title equipped.", ephemeral=True)

    @title.command(name="unequip", description="Remove your equipped title.")
    async def unequip(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.bot.titles_store.set_equipped(interaction.guild.id, interaction.user.id, "")  # type: ignore[attr-defined]
        await interaction.followup.send("Title removed.", ephemeral=True)

    # Command group is automatically registered by discord.py
