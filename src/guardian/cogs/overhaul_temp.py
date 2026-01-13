from __future__ import annotations

import asyncio
import time
from typing import Optional, Dict, Any, List
import discord
from discord import app_commands
from discord.ext import commands
import logging

from guardian.cogs.overhaul_prod import OverhaulEngine, OverhaulConfig, OverhaulCog as ProductionOverhaulCog
from guardian.observability import observability, log_command_execution
from guardian.security.permissions import admin_command

log = logging.getLogger("guardian.overhaul_temp")


class OverhaulTempCog(commands.Cog):
    """Temporary wrapper for production overhaul system - REMOVES AFTER USE."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Initialize production engine with default config
        self.production_engine = OverhaulEngine(bot)
    
    async def cog_load(self) -> None:
        """Initialize cog."""
        log.info("OverhaulTempCog loaded - TEMPORARY COG")
    
    @app_commands.command(
        name="overhaul", 
        description="TEMPORARY: Complete server overhaul - DELETES EVERYTHING and rebuilds clean architecture"
    )
    @admin_command()
    async def overhaul(self, interaction: discord.Interaction) -> None:
        """Initiate server overhaul using production engine."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        
        # Defer to avoid timeout
        await interaction.response.defer(ephemeral=True)
        
        # Create confirmation embed
        embed = discord.Embed(
            title="⚠️ SERVER OVERHAUL CONFIRMATION",
            description=(
                "**THIS WILL DELETE EVERYTHING AND REBUILD THE SERVER**\n\n"
                "**What will be deleted:**\n"
                "• All channels and categories\n"
                "• All roles (except @everyone, managed roles, and roles above bot)\n\n"
                "**What will be created:**\n"
                "• Clean role-based architecture\n"
                "• Verification system\n"
                "• Support channels\n"
                "• Game and interest spaces\n"
                "• Optimized permissions\n\n"
                "**⚠️ THIS ACTION IS IRREVERSIBLE.**\n\n"
                "**Production Features:**\n"
                "• Batch operations for speed\n"
                "• Error handling and recovery\n"
                "• Progress tracking\n"
                "• Configurable preservation options\n\n"
                "This temporary command will be removed after use.\n"
                "Consider using the production overhaul system instead."
            ),
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="🔧 Production Features",
            value=(
                "✅ Rate limiting and retry logic\n"
                "✅ Comprehensive error handling\n"
                "✅ Progress tracking\n"
                "✅ Configurable options\n"
                "✅ Optimized role hierarchy\n"
                "✅ Batch processing"
            ),
            inline=False
        )
        
        embed.set_footer(text="This command is temporary and will be removed after use")
        
        # Create confirmation view
        view = OverhaulConfirmationView()
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
        # Log the command
        log_command_execution(
            "overhaul_temp",
            user=interaction.user,
            guild=interaction.guild,
            success=True
        )


class OverhaulConfirmationView(discord.ui.View):
    """Confirmation view for temporary overhaul command."""
    
    def __init__(self):
        super().__init__(timeout=300)  # 5 minutes timeout
    
    @discord.ui.button(
        label="Confirm Overhaul",
        style=discord.ButtonStyle.danger,
        custom_id="overhaul_confirm"
    )
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm and execute overhaul."""
        await interaction.response.edit_message(
            content="✅ **Overhaul confirmed. Starting production-grade process...**",
            embed=None,
            view=None
        )
        
        # Stop this view
        self.stop()
        
        # Get the temporary cog
        temp_cog = interaction.client.get_cog('OverhaulTempCog')
        if temp_cog:
            # Execute using production engine
            result = await temp_cog.production_engine.execute_overhaul(interaction)
            
            # Send final result
            if result.success:
                embed = discord.Embed(
                    title="✅ Production Overhaul Complete",
                    description=(
                        f"**Phase:** {result.phase.title()}\n\n"
                        f"**Deleted:** {result.deleted['channels']} channels, {result.deleted['categories']} categories, {result.deleted['roles']} roles\n"
                        f"**Created:** {result.created['categories']} categories, {result.created['channels']} channels, {result.created['roles']} roles\n"
                        f"**Duration:** {result.duration_ms:.0f}ms"
                    ),
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Production Overhaul Failed",
                    description=(
                        f"**Phase:** {result.phase.title()}\n\n"
                        f"**Errors:** {len(result.errors)}\n"
                        f"**Duration:** {result.duration_ms:.0f}ms"
                    ),
                    color=discord.Color.red()
                )
            
            if result.errors:
                embed.add_field(
                    name="Errors",
                    value="\n".join(result.errors[:5]),  # Limit to first 5 errors
                    inline=False
                )
            
            if result.warnings:
                embed.add_field(
                    name="Warnings", 
                    value="\n".join(result.warnings),
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send("❌ Production overhaul system not available.", ephemeral=True)
    
    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="overhaul_cancel"
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel overhaul confirmation."""
        await interaction.response.edit_message(
            content="❌ **Overhaul cancelled.**",
            embed=None,
            view=None
        )
        
        # Stop this view
        self.stop()


# Setup function for adding cog
async def setup(bot: commands.Bot) -> None:
    """Add overhaul temp cog to bot."""
    await bot.add_cog(OverhaulTempCog(bot))
    log.warning("OverhaulTempCog added - REMEMBER TO REMOVE THIS TEMPORARY COG")
