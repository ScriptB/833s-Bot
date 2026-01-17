from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from ..lookup import find_text_channel

from ..permissions import require_verified


class SuggestionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.command(name="suggest", description="Create a suggestion and post it in #suggestions.")
    @require_verified()
    async def suggest(self, interaction: discord.Interaction, text: str) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        ch = find_text_channel(interaction.guild, "suggestions") or find_text_channel(interaction.guild, "general-chat")
        if not isinstance(ch, discord.TextChannel):
            await interaction.followup.send("❌ #suggestions not found.", ephemeral=True)
            return

        sid = await self.bot.suggestions_store.add(interaction.guild.id, interaction.user.id, text)  # type: ignore[attr-defined]
        e = discord.Embed(title=f"Suggestion #{sid}", description=text[:3800])
        e.set_footer(text=f"By {interaction.user} • React 👍/👎")
        msg = await ch.send(embed=e)
        try:
            await msg.add_reaction("👍")
            await msg.add_reaction("👎")
        except discord.HTTPException:
            pass
        await self.bot.suggestions_store.set_message(interaction.guild.id, sid, msg.id)  # type: ignore[attr-defined]
        await interaction.followup.send(f"✅ Posted suggestion #{sid}.", ephemeral=True)
