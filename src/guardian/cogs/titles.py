from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands

from ..permissions import require_verified


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

    # Individual commands instead of group (app_commands.Group not available in this version)

    async def _level(self, guild_id: int, user_id: int) -> int:
        _, _, lvl = await self.bot.levels_store.get(guild_id, user_id)  # type: ignore[attr-defined]
        return int(lvl)

    def _unlocked(self, lvl: int) -> list[str]:
        return [t for min_lvl, t in TITLE_CATALOG if lvl >= min_lvl]

    def _has_staff_role(self, member: discord.Member) -> bool:
        """Check if member has Staff or Moderator role."""
        staff_roles = ["Staff", "Moderator"]
        return any(role.name in staff_roles for role in member.roles)

    @app_commands.command(name="titles_list", description="List titles you can equip.")
    @require_verified()
    async def list_titles(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        
        if not self._has_staff_role(interaction.user):
            await interaction.response.send_message("This command requires Staff or Moderator role.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
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

    @app_commands.command(name="titles_equip", description="Equip a title you have unlocked.")
    @require_verified()
    async def equip(self, interaction: discord.Interaction, title: str) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        
        if not self._has_staff_role(interaction.user):
            await interaction.response.send_message("This command requires Staff or Moderator role.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
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

    @app_commands.command(name="titles_unequip", description="Remove your equipped title.")
    @require_verified()
    async def unequip(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        
        if not self._has_staff_role(interaction.user):
            await interaction.response.send_message("This command requires Staff or Moderator role.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        await self.bot.titles_store.set_equipped(interaction.guild.id, interaction.user.id, "")  # type: ignore[attr-defined]
        await interaction.followup.send("Title removed.", ephemeral=True)

    # Command group is automatically registered by discord.py
