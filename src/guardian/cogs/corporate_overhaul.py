from __future__ import annotations

import logging
import traceback
import discord
from discord import app_commands
from discord.ext import commands

from ..ui.overhaul_production_v4 import ProductionOverhaulExecutor
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
        
        # Execute production overhaul
        try:
            self.current_executor = ProductionOverhaulExecutor(self, guild, {})
            
            # Set up progress tracking
            self.current_executor.progress_tracker.set_user(interaction.user)
            
            # Run the overhaul
            result = await self.current_executor.run()
            self.current_executor = None
            
            # Try to send completion message
            try:
                # Truncate result if too long for Discord
                if len(result) > 1900:  # Leave room for prefix
                    truncated_result = result[:1900] + "\n\n... (truncated for length)"
                    completion_msg = f"✅ **Robust Overhaul completed**\n\n{truncated_result}"
                else:
                    completion_msg = f"✅ **Robust Overhaul completed**\n\n{result}"
                
                # Check if response was already sent
                if interaction.response.is_done():
                    await interaction.followup.send(completion_msg, ephemeral=True)
                else:
                    await interaction.response.send_message(completion_msg, ephemeral=True)
                    
            except discord.NotFound:
                # Interaction expired, log success
                log.info(f"Robust overhaul completed for guild {guild.name} but interaction expired")
            except discord.InteractionResponded:
                # Already responded, try followup
                try:
                    await interaction.followup.send(completion_msg, ephemeral=True)
                except:
                    log.info(f"Robust overhaul completed for guild {guild.name} but couldn't send followup")
            except Exception as e2:
                log.error(f"Failed to send completion message: {e2}")
            
        except Exception as e:
            log.error(f"Production overhaul failed: {e}")
            log.error(f"Traceback: {traceback.format_exc()}")
            
            error_msg = f"❌ **Production Overhaul failed**: {str(e)}"
            await self._send_safe_message(interaction, error_msg, success=False)
            
            self.current_executor = None
    
    async def _send_safe_message(self, interaction: discord.Interaction, content: str, success: bool):
        """Send message safely with length limits and fallbacks."""
        try:
            # Ensure content is under Discord limit
            if len(content) > 1900:
                # Create summary
                summary = content[:1900] + "\n\n... (truncated for length)"
                
                # Try to send as file attachment for full report
                try:
                    import io
                    file_content = content.encode('utf-8')
                    file = discord.File(
                        io.BytesIO(file_content),
                        filename="overhaul_report.txt"
                    )
                    
                    await interaction.followup.send(
                        content=summary,
                        file=file,
                        ephemeral=True
                    )
                except Exception as file_error:
                    log.warning(f"Failed to send file attachment: {file_error}")
                    # Fallback to truncated message
                    await interaction.followup.send(content=summary, ephemeral=True)
            else:
                # Normal length message
                await interaction.followup.send(content, ephemeral=True)
                    
        except discord.NotFound:
            log.warning("Interaction expired, could not send completion message")
        except discord.Forbidden:
            log.warning("Missing permissions to send completion message")
        except Exception as e:
            log.error(f"Failed to send completion message: {e}")
    
    def cog_unload(self):
        """Handle cog unload - cancel any running overhaul."""
        if self.current_executor:
            self.current_executor.cancel()
            self.current_executor = None
