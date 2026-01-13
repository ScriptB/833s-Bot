from __future__ import annotations

import asyncio
import time
from typing import Optional, Dict, Any, List
import discord
from discord import app_commands
from discord.ext import commands
import logging

from ..overhaul.engine import OverhaulEngine
from ..overhaul.progress import ProgressReporter
from ..overhaul.rate_limiter import RateLimiter
from ..interfaces import validate_progress_reporter

log = logging.getLogger("guardian.overhaul_temp")


class OverhaulTempCog(commands.Cog):
    """TEMPORARY cog for server overhaul functionality. REMOVE AFTER USE."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rate_limiter = RateLimiter()
        self.pending_confirmations: Dict[int, discord.Interaction] = {}
    
    async def cog_load(self) -> None:
        """Initialize cog."""
        log.info("OverhaulTempCog loaded - TEMPORARY COG")
    
    @app_commands.command(
        name="overhaul", 
        description="TEMPORARY: Complete server overhaul - DELETES EVERYTHING and rebuilds clean architecture"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def overhaul(self, interaction: discord.Interaction) -> None:
        """Initiate server overhaul with confirmation gate."""
        await self._handle_overhaul_request(interaction)
    
    async def _handle_overhaul_request(self, interaction: discord.Interaction) -> None:
        """Handle initial overhaul request with confirmation gate."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        
        # Check if already pending
        if interaction.user.id in self.pending_confirmations:
            await interaction.response.send_message(
                "You already have a pending overhaul confirmation. Please wait for it to expire.",
                ephemeral=True
            )
            return
        
        # Create confirmation view
        view = OverhaulConfirmationView(self, interaction.user.id)
        
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
                "• Game and interest spaces\n\n"
                "**This action is IRREVERSIBLE.**\n\n"
                "Click **Confirm** to proceed or wait 60 seconds to cancel."
            ),
            color=discord.Color.red()
        )
        embed.set_footer(text="This command is temporary and will be removed after use")
        
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
        # Store pending confirmation
        self.pending_confirmations[interaction.user.id] = interaction
        
        # Auto-cancel after 60 seconds
        await asyncio.sleep(60)
        if interaction.user.id in self.pending_confirmations:
            del self.pending_confirmations[interaction.user.id]
            log.info(f"Overhaul confirmation expired for user {interaction.user.id}")
    
    async def execute_overhaul(self, interaction: discord.Interaction) -> None:
        """Execute the actual overhaul process."""
        if not interaction.guild:
            return
        
        # Remove from pending
        self.pending_confirmations.pop(interaction.user.id, None)
        
        # Initialize components
        engine = OverhaulEngine(self.bot, self.rate_limiter)
        reporter = ProgressReporter(interaction)
        
        # Validate interface compliance
        validate_progress_reporter(reporter)
        
        try:
            # Phase A: Validation
            await reporter.init()
            await reporter.update("Validating", 0, 1, "Checking permissions")
            validation_result = await engine.validate(interaction.guild)
            if not validation_result.ok:
                await reporter.finalize(False, f"Validation failed: {validation_result.reason}")
                return
            
            # Phase B: Snapshot
            await reporter.update("Snapshot", 0, 1, "Counting existing items")
            snapshot = await engine.snapshot(interaction.guild)
            
            # Phase C: Deletion
            await reporter.update("Deleting", 0, 1, "Starting deletion")
            delete_result = await engine.delete_all(interaction.guild, reporter)
            
            # Verify deletion actually happened
            deletion_ok, deletion_msg = snapshot.verify_deletion(
                delete_result.channels_deleted,
                delete_result.categories_deleted,
                delete_result.roles_deleted
            )
            
            if not deletion_ok:
                await reporter.finalize(False, f"Deletion failed: {deletion_msg}")
                return
            
            # Phase D: Rebuilding
            await reporter.update("Rebuilding", 0, 1, "Starting rebuild")
            rebuild_result = await engine.rebuild_all(interaction.guild, reporter)
            
            # Phase E: Content posting
            await reporter.update("Posting channel posts", 0, 1, "Starting content posting")
            content_result = await engine.post_content(interaction.guild, reporter)
            
            final_summary = (
                f"Deleted: {delete_result.channels_deleted} channels, {delete_result.categories_deleted} categories, {delete_result.roles_deleted} roles. "
                f"Created: {rebuild_result.categories_created} categories, {rebuild_result.channels_created} channels, {rebuild_result.roles_created} roles. "
                f"Posted: {content_result.posts_created} content messages."
            )
            await reporter.finalize(True, final_summary)
            
        except Exception as e:
            log.exception(f"Critical error during overhaul: {e}")
            await reporter.finalize(False, f"Critical error: {str(e)}")
    
    async def cog_unload(self) -> None:
        """Cleanup when cog is unloaded."""
        log.info("OverhaulTempCog unloaded - TEMPORARY COG REMOVED")


class OverhaulConfirmationView(discord.ui.View):
    """Confirmation view for overhaul command."""
    
    def __init__(self, cog: OverhaulTempCog, user_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow original user to confirm."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the command invoker can confirm this action.", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(
        label="Confirm Overhaul",
        style=discord.ButtonStyle.danger,
        custom_id="overhaul_confirm"
    )
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Confirm and execute overhaul."""
        await interaction.response.edit_message(
            content="✅ **Overhaul confirmed. Starting process...**",
            embed=None,
            view=None
        )
        
        # Stop this view
        self.stop()
        
        # Execute overhaul
        await self.cog.execute_overhaul(interaction)
    
    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="overhaul_cancel"
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Cancel overhaul confirmation."""
        await interaction.response.edit_message(
            content="❌ **Overhaul cancelled.**",
            embed=None,
            view=None
        )
        
        # Remove from pending
        self.cog.pending_confirmations.pop(self.user_id, None)
        
        # Stop this view
        self.stop()


# Setup function for adding cog
async def setup(bot: commands.Bot) -> None:
    """Add overhaul temp cog to bot."""
    await bot.add_cog(OverhaulTempCog(bot))
    log.warning("OverhaulTempCog added - REMEMBER TO REMOVE THIS TEMPORARY COG")
