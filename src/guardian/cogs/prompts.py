from __future__ import annotations

import datetime
import discord
from discord import app_commands
from discord.ext import commands


class PromptsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    prompt = app_commands.Group(name="community_prompt", description="Community prompts.")

    async def _level(self, guild_id: int, user_id: int) -> int:
        _, _, lvl = await self.bot.levels_store.get(guild_id, user_id)  # type: ignore[attr-defined]
        return int(lvl)

    @prompt.command(name="submit", description="Submit a new community prompt (level 2+).")
    async def submit(self, interaction: discord.Interaction, text: str) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        if await self._level(interaction.guild.id, interaction.user.id) < 2:
            await interaction.followup.send("Requires level 2.", ephemeral=True)
            return
        try:
            pid = await self.bot.prompts_store.submit_prompt(interaction.guild.id, interaction.user.id, text)  # type: ignore[attr-defined]
            try:
                await self.bot.community_memory_store.add(interaction.guild.id, "prompt_submit", {"user_id": interaction.user.id, "prompt_id": pid})  # type: ignore[attr-defined]
            except Exception:
                pass
            await interaction.followup.send(f"Prompt submitted (ID {pid}).", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Prompt text required.", ephemeral=True)

    @prompt.command(name="current", description="Show the latest prompt.")
    async def current(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        p = await self.bot.prompts_store.get_current(interaction.guild.id)  # type: ignore[attr-defined]
        if not p:
            await interaction.followup.send("No prompts yet.", ephemeral=True)
            return
        emb = discord.Embed(title=f"Prompt #{p.prompt_id}", description=p.text)
        emb.set_footer(text=f"Created at {datetime.datetime.utcfromtimestamp(p.created_at).isoformat()}Z")
        await interaction.followup.send(embed=emb, ephemeral=True)

    @prompt.command(name="answer", description="Answer the latest prompt.")
    async def answer(self, interaction: discord.Interaction, text: str) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        p = await self.bot.prompts_store.get_current(interaction.guild.id)  # type: ignore[attr-defined]
        if not p:
            await interaction.followup.send("No prompt to answer.", ephemeral=True)
            return
        try:
            aid = await self.bot.prompts_store.add_answer(interaction.guild.id, p.prompt_id, interaction.user.id, text)  # type: ignore[attr-defined]
            try:
                await self.bot.community_memory_store.add(interaction.guild.id, "prompt_answer", {"user_id": interaction.user.id, "prompt_id": p.prompt_id, "answer_id": aid})  # type: ignore[attr-defined]
            except Exception:
                pass
            await interaction.followup.send("Answer saved.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Answer text required.", ephemeral=True)

    @prompt.command(name="history", description="Show recent prompts.")
    async def history(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10] = 5) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        items = await self.bot.prompts_store.history(interaction.guild.id, int(limit))  # type: ignore[attr-defined]
        if not items:
            await interaction.followup.send("No prompts yet.", ephemeral=True)
            return
        lines = [f"#{p.prompt_id}: {p.text[:80]}" for p in items]
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # Command group is automatically registered by discord.py
