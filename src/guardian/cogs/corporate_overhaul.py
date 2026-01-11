from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..ui.overhaul_authoritative import AuthoritativeOverhaulExecutor
from ..services.schema import canonical_schema
from ..services.schema_builder import SchemaBuilder


class CorporateOverhaulCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self.progress_user = None  # Store for progress tracking

    @app_commands.command(name="overhaul", description="Execute authoritative server overhaul (Root only)")
    @commands.is_owner()
    async def overhaul(self, interaction: discord.Interaction) -> None:
        """Execute authoritative server overhaul with real, enforceable design."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Validate user is root operator
        if not await self._is_root_operator(interaction.user.id):
            await interaction.followup.send(
                "❌ This command is restricted to root operators only.",
                ephemeral=True
            )
            return
        
        # Get guild
        if not interaction.guild:
            await interaction.followup.send(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return
        
        guild = interaction.guild
        
        # Execute authoritative overhaul
        try:
            executor = AuthoritativeOverhaulExecutor(self, guild, {})
            executor.progress_user = interaction.user  # Set progress recipient
            result = await executor.run()
            
            await interaction.followup.send(
                f"✅ **Authoritative Overhaul completed**\n\n{result}",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ **Authoritative Overhaul failed**: {e}",
                ephemeral=True
            )
    
    async def _is_root_operator(self, user_id: int) -> bool:
        """Check if user is a root operator."""
        try:
            if hasattr(self.bot, 'root_store'):
                root_ops = await self.bot.root_store.get_all()
                return user_id in root_ops
            return False
        except Exception:
            return False
