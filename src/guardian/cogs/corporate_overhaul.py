from __future__ import annotations

import logging
import discord
from discord import app_commands
from discord.ext import commands

from ..ui.overhaul_robust import RobustOverhaulExecutor
from ..security.auth import root_only

log = logging.getLogger("guardian.corporate_overhaul")


class CorporateOverhaulCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self.progress_user = None  # Store for progress tracking
        self.interaction = None  # Store interaction for fallback
        self.current_executor = None  # Store current executor for cancellation

    @app_commands.command(name="overhaul", description="Execute template-based server overhaul (Root only)")
    @root_only()
    async def overhaul(self, interaction: discord.Interaction) -> None:
        """Execute template-based server overhaul with exact structure matching."""
        # Store interaction for fallback
        self.interaction = interaction
        self.progress_user = interaction.user
        
        # Get guild
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return
        
        guild = interaction.guild
        
        # Send initial response
        try:
            await interaction.response.send_message(
                "🏰 **Template Overhaul Started**\n\n"
                "You will receive real-time progress updates via DM.\n"
                "This process will take several minutes...",
                ephemeral=True
            )
        except discord.NotFound:
            # Interaction already expired, continue anyway
            log.warning("Interaction expired before response could be sent")
        
        # Execute template overhaul
        try:
            self.current_executor = RobustOverhaulExecutor(self, guild, {})
            self.current_executor.progress_user = interaction.user  # Set progress recipient
            result = await self.current_executor.run()
            self.current_executor = None
            
            # Try to send completion message
            try:
                # Truncate result if too long for Discord
                if len(result) > 1900:  # Leave room for prefix
                    truncated_result = result[:1900] + "\n\n... (truncated for length)"
                    completion_msg = f"✅ **Template Overhaul completed**\n\n{truncated_result}"
                else:
                    completion_msg = f"✅ **Template Overhaul completed**\n\n{result}"
                
                if interaction.response.is_done():
                    await interaction.followup.send(completion_msg, ephemeral=True)
                else:
                    await interaction.response.send_message(completion_msg, ephemeral=True)
            except discord.NotFound:
                # Interaction expired, log completion
                log.info(f"Template overhaul completed for guild {guild.name} but interaction expired")
            except Exception as e:
                log.error(f"Failed to send completion message: {e}")
            
        except Exception as e:
            # Try to send error message
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        f"❌ **Template Overhaul failed**: {e}",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ **Template Overhaul failed**: {e}",
                        ephemeral=True
                    )
            except discord.NotFound:
                # Interaction expired, log error
                log.error(f"Template overhaul failed for guild {guild.name} but interaction expired: {e}")
            except Exception as e2:
                log.error(f"Failed to send error message: {e2}")
            
            # Re-raise the original error
            raise
        finally:
            self.current_executor = None
    
    def cog_unload(self):
        """Handle cog unload - cancel any running overhaul."""
        if self.current_executor:
            self.current_executor.cancel()
            self.current_executor = None
