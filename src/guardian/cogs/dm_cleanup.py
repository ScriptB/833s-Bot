from __future__ import annotations

import asyncio
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from ..utils import safe_embed, success_embed, error_embed, warning_embed
from ..constants import COLORS


class DMCleanupCog(commands.Cog):
    """Cog for cleaning up bot messages in direct messages."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
    
    @app_commands.command(
        name="dm_cleanup",
        description="Delete all bot messages in this DM channel (Owner only)",
    )
    async def dm_cleanup(self, interaction: discord.Interaction) -> None:
        """Clean up all bot messages in the current DM channel."""
        
        # Only allow in DMs
        if not isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message(
                "❌ This command can only be used in direct messages.", 
                ephemeral=True
            )
            return
        
        # Only allow server owner to use this command
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message(
                "❌ Only the bot owner can use this command.", 
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            deleted_count = await self._cleanup_dm_messages(interaction.channel)
            
            if deleted_count > 0:
                embed = success_embed("🧹 DM Cleanup Complete")
                embed.description = f"Successfully deleted **{deleted_count}** bot messages from this DM channel."
                embed.add_field(name="Channel", value=f"DM with {self.bot.user.mention}", inline=True)
                embed.add_field(name="Messages Deleted", value=str(deleted_count), inline=True)
                embed.add_field(name="Status", value="✅ Clean", inline=True)
                
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = warning_embed("🧹 DM Cleanup - No Messages Found")
                embed.description = "No bot messages found to delete in this DM channel."
                embed.add_field(name="Status", value="✅ Already Clean", inline=True)
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Cannot delete messages - insufficient permissions in this DM channel.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ Failed to clean up messages: {e}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Unexpected error during cleanup: {type(e).__name__}: {e}",
                ephemeral=True
            )
    
    async def _cleanup_dm_messages(self, dm_channel: discord.DMChannel) -> int:
        """Systematically delete all bot messages in the DM channel."""
        deleted_count = 0
        
        try:
            # Get message history (up to 1000 messages to be thorough)
            async for message in dm_channel.history(limit=1000):
                # Check if message is from bot
                if message.author == self.bot.user:
                    try:
                        await message.delete()
                        deleted_count += 1
                        # Add small delay to avoid rate limits
                        await asyncio.sleep(0.1)
                    except discord.NotFound:
                        # Message already deleted
                        continue
                    except discord.Forbidden:
                        # Cannot delete this specific message
                        continue
                    except discord.HTTPException:
                        # Rate limited or other API error
                        await asyncio.sleep(1)
                        continue
                    except Exception:
                        # Unexpected error with this message
                        continue
                        
        except discord.Forbidden:
            # Cannot access message history
            raise
        except discord.HTTPException:
            # API error fetching history
            raise
        except Exception:
            # Unexpected error
            raise
        
        return deleted_count
    
    @app_commands.command(
        name="dm_cleanup_bulk",
        description="Delete bot messages from all DM channels (Owner only)",
    )
    async def dm_cleanup_bulk(self, interaction: discord.Interaction) -> None:
        """Clean up bot messages from all DM channels."""
        
        # Only allow server owner to use this command
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message(
                "❌ Only the bot owner can use this command.", 
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            total_deleted = 0
            failed_channels = 0
            
            # Get all DM channels the bot has access to
            # Note: This is limited as Discord doesn't provide a direct way to list all DM channels
            # We'll work with the bot's cached DM channels
            
            embed = warning_embed("🧹 Bulk DM Cleanup Started")
            embed.description = "Starting bulk cleanup of bot messages from all accessible DM channels..."
            embed.add_field(name="Status", value="🔄 In Progress", inline=True)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Get all private channels (DMs) from bot's cache
            dm_channels = [channel for channel in self.bot.private_channels if isinstance(channel, discord.DMChannel)]
            
            for dm_channel in dm_channels:
                try:
                    deleted = await self._cleanup_dm_messages(dm_channel)
                    total_deleted += deleted
                    
                    # Send progress update
                    if total_deleted % 10 == 0:  # Update every 10 messages deleted
                        progress_embed = info_embed("🧹 Bulk DM Cleanup Progress")
                        progress_embed.description = f"Deleted **{total_deleted}** messages so far..."
                        progress_embed.add_field(name="Channels Checked", value=str(len(dm_channels)), inline=True)
                        progress_embed.add_field(name="Messages Deleted", value=str(total_deleted), inline=True)
                        progress_embed.add_field(name="Status", value="🔄 In Progress", inline=True)
                        
                        await interaction.followup.send(embed=progress_embed, ephemeral=True)
                        
                except Exception as e:
                    failed_channels += 1
                    continue
            
            # Final report
            if total_deleted > 0:
                final_embed = success_embed("🧹 Bulk DM Cleanup Complete")
                final_embed.description = f"Successfully deleted **{total_deleted}** bot messages from **{len(dm_channels)}** DM channels."
                final_embed.add_field(name="Total Messages Deleted", value=str(total_deleted), inline=True)
                final_embed.add_field(name="Channels Processed", value=str(len(dm_channels)), inline=True)
                final_embed.add_field(name="Failed Channels", value=str(failed_channels), inline=True)
                final_embed.add_field(name="Status", value="✅ Complete", inline=False)
                
                await interaction.followup.send(embed=final_embed, ephemeral=True)
            else:
                final_embed = warning_embed("🧹 Bulk DM Cleanup - No Messages Found")
                final_embed.description = "No bot messages found to delete in any DM channels."
                final_embed.add_field(name="Status", value="✅ Already Clean", inline=True)
                
                await interaction.followup.send(embed=final_embed, ephemeral=True)
                
        except Exception as e:
            error_embed_msg = error_embed("❌ Bulk DM Cleanup Failed")
            error_embed_msg.description = f"Failed to perform bulk cleanup: {type(e).__name__}: {e}"
            await interaction.followup.send(embed=error_embed_msg, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Setup the DM cleanup cog."""
    await bot.add_cog(DMCleanupCog(bot))
