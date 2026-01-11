from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..ui.overhaul_template import TemplateOverhaulExecutor
from ..security.auth import root_only


class CorporateOverhaulCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self.progress_user = None  # Store for progress tracking
        self.interaction = None  # Store interaction for fallback

    @app_commands.command(name="overhaul", description="Execute template-based server overhaul (Root only)")
    @root_only()
    async def overhaul(self, interaction: discord.Interaction) -> None:
        """Execute template-based server overhaul with exact structure matching."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Store interaction for fallback
        self.interaction = interaction
        self.progress_user = interaction.user
        
        # Get guild
        if not interaction.guild:
            await interaction.followup.send(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return
        
        guild = interaction.guild
        
        # Execute template overhaul
        try:
            executor = TemplateOverhaulExecutor(self, guild, {})
            executor.progress_user = interaction.user  # Set progress recipient
            result = await executor.run()
            
            await interaction.followup.send(
                f"✅ **Template Overhaul completed**\n\n{result}",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ **Template Overhaul failed**: {e}",
                ephemeral=True
            )
