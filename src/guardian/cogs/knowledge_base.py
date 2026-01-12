from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


ARTICLES = {
    "server-guide": [
        ("Welcome", "Use #announcements for updates. Complete onboarding in #verify. Use /help_commands for bot features."),
        ("Channels", "Post in the right channels. Use #showcase for projects. Use #help or tickets for support."),
        ("Safety", "Avoid unknown links. Report issues via tickets or staff."),
    ],
    "faq": [
        ("How do I get access?", "Complete onboarding in #verify. You will receive Verified + Member roles."),
        ("How do tickets work?", "Use the button in #tickets. A private channel will be created for you."),
        ("How does leveling work?", "Activity earns XP with cooldown and anti-farm logic. Level roles unlock automatically."),
    ],
}


class KnowledgeBaseCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.command(name="kb", description="Open the knowledge base.")
    async def kb(self, interaction: discord.Interaction, article: str) -> None:
        await interaction.response.defer(ephemeral=True)
        key = article.strip().lower()
        if key not in ARTICLES:
            await interaction.followup.send("Unknown article. Options: server-guide, faq", ephemeral=True)
            return
        e = discord.Embed(title=f"Knowledge Base: {key}")
        for h, b in ARTICLES[key]:
            e.add_field(name=h, value=b[:900], inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="kb_search", description="Search the knowledge base by keyword.")
    async def kb_search(self, interaction: discord.Interaction, keyword: str) -> None:
        await interaction.response.defer(ephemeral=True)
        k = keyword.strip().lower()
        hits = []
        for name, sections in ARTICLES.items():
            for h, b in sections:
                if k in h.lower() or k in b.lower():
                    hits.append((name, h))
        if not hits:
            await interaction.followup.send("No results.", ephemeral=True)
            return
        e = discord.Embed(title=f"KB Search: {keyword}")
        e.description = "\n".join([f"• **{a}** → {h}" for a, h in hits[:20]])
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="help_commands", description="List key commands.")
    async def help_commands(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        e = discord.Embed(title="833s Guardian Commands")
        e.add_field(name="Setup", value="/guardian_rebuild, /guardian_validate, /ticket_panel", inline=False)
        e.add_field(name="Moderation", value="/warn, /timeout, /purge, /cases", inline=False)
        e.add_field(name="Community", value="/rep, /rep_show, /suggest, /kb, /kb_search", inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)
