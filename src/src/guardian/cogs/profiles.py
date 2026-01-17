from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..permissions import require_verified


class ProfilesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.command(name="user_profile", description="View a member's community profile.")
    @require_verified()
    async def user_profile(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        member = member or interaction.user  # type: ignore[assignment]
        prof = await self.bot.profiles_store.get(interaction.guild.id, member.id)  # type: ignore[attr-defined]
        title_state = await self.bot.titles_store.get(interaction.guild.id, member.id)  # type: ignore[attr-defined]
        rep = await self.bot.reputation_store.get(interaction.guild.id, member.id)  # type: ignore[attr-defined]
        _, xp, lvl = await self.bot.levels_store.get(interaction.guild.id, member.id)  # type: ignore[attr-defined]

        if not prof.is_public and member.id != interaction.user.id:
            await interaction.followup.send("This profile is private.", ephemeral=True)
            return

        emb = discord.Embed(title=f"Profile: {member.display_name}")
        if title_state.equipped:
            emb.add_field(name="Title", value=title_state.equipped, inline=True)
        emb.add_field(name="Level", value=str(int(lvl)), inline=True)
        emb.add_field(name="XP", value=str(int(xp)), inline=True)
        emb.add_field(name="Reputation", value=str(int(rep)), inline=True)

        if prof.pronouns:
            emb.add_field(name="Pronouns", value=prof.pronouns, inline=True)
        if prof.about:
            emb.add_field(name="About", value=prof.about[:500], inline=False)
        if prof.interests:
            emb.add_field(name="Interests", value=", ".join(prof.interests), inline=False)

        await interaction.followup.send(embed=emb, ephemeral=True)

    @app_commands.command(name="profile_edit_about", description="Set your profile about text.")
    @require_verified()
    async def edit_about(self, interaction: discord.Interaction, about: str) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        about = (about or "").strip()
        await self.bot.profiles_store.upsert(interaction.guild.id, interaction.user.id, about=about)  # type: ignore[attr-defined]
        try:
            await self.bot.community_memory_store.add(interaction.guild.id, "profile_about", {"user_id": interaction.user.id})  # type: ignore[attr-defined]
        except Exception:
            pass
        await interaction.followup.send("Profile updated.", ephemeral=True)

    @app_commands.command(name="profile_edit_pronouns", description="Set your pronouns.")
    @require_verified()
    async def edit_pronouns(self, interaction: discord.Interaction, pronouns: str) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        pronouns = (pronouns or "").strip()
        await self.bot.profiles_store.upsert(interaction.guild.id, interaction.user.id, pronouns=pronouns)  # type: ignore[attr-defined]
        try:
            await self.bot.community_memory_store.add(interaction.guild.id, "profile_pronouns", {"user_id": interaction.user.id})  # type: ignore[attr-defined]
        except Exception:
            pass
        await interaction.followup.send("Profile updated.", ephemeral=True)

    @app_commands.command(name="profile_edit_interests", description="Set your interests (comma-separated, up to 12).")
    @require_verified()
    async def edit_interests(self, interaction: discord.Interaction, interests: str) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        raw = (interests or "").strip()
        items = [p.strip() for p in raw.split(",") if p.strip()]
        await self.bot.profiles_store.upsert(interaction.guild.id, interaction.user.id, interests=items)  # type: ignore[attr-defined]
        try:
            await self.bot.community_memory_store.add(interaction.guild.id, "profile_interests", {"user_id": interaction.user.id})  # type: ignore[attr-defined]
        except Exception:
            pass
        await interaction.followup.send("Profile updated.", ephemeral=True)

    @app_commands.command(name="profile_privacy", description="Set your profile visibility.")
    @require_verified()
    async def privacy(self, interaction: discord.Interaction, public: bool) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        await self.bot.profiles_store.upsert(interaction.guild.id, interaction.user.id, is_public=bool(public))  # type: ignore[attr-defined]
        await interaction.followup.send("Privacy updated.", ephemeral=True)

    # Command group is automatically registered by discord.py
