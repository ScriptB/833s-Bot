"""
Overhaul Cog

The single, clean overhaul command implementation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..overhaul.engine import OverhaulEngine
from ..overhaul.reporting import send_safe_message
from ..security.auth import root_only

log = logging.getLogger("guardian.overhaul.cog")


class ConfirmationView(discord.ui.View):
    """Confirmation view for overhaul command."""
    
    def __init__(self):
        super().__init__(timeout=60)
        self.value: Optional[bool] = None
    
    @button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Overhaul confirmed, starting...", ephemeral=True)
        self.value = True
        self.stop()
    
    @button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Overhaul cancelled.", ephemeral=True)
        self.value = False
        self.stop()


class OverhaulCog(commands.Cog):
    """Overhaul command cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.current_engine: Optional[OverhaulEngine] = None
    
    @app_commands.command(name="overhaul", description="Execute complete server overhaul (Bot owner only)")
    @root_only()
    async def overhaul(self, interaction: discord.Interaction) -> None:
        """Execute a complete server overhaul."""
        
        # Check guild
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return
        
        guild = interaction.guild
        
        # Send initial confirmation request
        embed = discord.Embed(
            title="⚠️ SERVER OVERHAUL CONFIRMATION",
            description=(
                "This will **completely wipe and rebuild** the server structure:\n\n"
                "• Delete all channels, categories, and roles\n"
                "• Create new emoji-based structure\n"
                "• Apply permissions and settings\n\n"
                "**This action cannot be undone!**"
            ),
            color=discord.Color.red()
        )
        
        view = ConfirmationView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        # Wait for confirmation
        await view.wait()
        
        if view.value is not True:
            return  # User cancelled
        
        # Get followup message for engine to use
        try:
            followup_msg = await interaction.followup.send("🏰 **Overhaul starting...**", ephemeral=True)
        except Exception as e:
            log.error(f"Failed to send followup: {e}")
            return
        
        # Execute overhaul with followup message
        try:
            self.current_engine = OverhaulEngine(guild)
            result = await self.current_engine.run(followup_msg)
            self.current_engine = None
            
            # Send completion message
            await send_safe_message(followup_msg, f"✅ **Overhaul Completed**\n\n{result}")
            
        except Exception as e:
            log.error(f"Overhaul failed: {e}")
            
            error_msg = f"❌ **Overhaul Failed**\n\nError: {str(e)}"
            await send_safe_message(followup_msg, error_msg)
            
            self.current_engine = None
    
    async def cog_unload(self):
        """Clean up when cog is unloaded."""
        if self.current_engine:
            self.current_engine.cancel()
            self.current_engine = None


async def setup(bot: commands.Bot) -> None:
    """Setup the overhaul cog."""
    await bot.add_cog(OverhaulCog(bot))
