from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

class SelfTestCog(commands.Cog):
    """Minimal self-test cog for Guardian bot."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
    
    @app_commands.command(name="selftest_ping", description="Test if selftest cog is loaded")
    async def selftest_ping(self, interaction: discord.Interaction) -> None:
        """Ping command to verify selftest cog is working."""
        await interaction.response.send_message("ok", ephemeral=True)
    
    @app_commands.command(name="selftest_sync", description="Resync commands without restart (Bot owner only)")
    async def selftest_sync(self, interaction: discord.Interaction) -> None:
        """Resync commands for testing."""
        # Check if user is bot owner
        try:
            app_info = await self.bot.application_info()
            if app_info.team:
                owner_ids = {member.id for member in app_info.team.members}
            else:
                owner_ids = {app_info.owner.id}
            
            if interaction.user.id not in owner_ids:
                await interaction.response.send_message(
                    "❌ This command is restricted to bot application owners only.",
                    ephemeral=True
                )
                return
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to verify ownership: {e}",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Check for optional guild sync setting
            sync_guild_id = getattr(self.bot.settings, 'sync_guild_id', None)
            if sync_guild_id:
                guild = discord.Object(id=sync_guild_id)
                synced_commands = await self.bot.tree.sync(guild=guild)
                await interaction.followup.send(
                    f"✅ **Commands synced to guild {sync_guild_id}**\n"
                    f"Synced commands: {len(synced_commands)}",
                    ephemeral=True
                )
            else:
                synced_commands = await self.bot.tree.sync()
                await interaction.followup.send(
                    f"✅ **Commands synced globally**\n"
                    f"Synced commands: {len(synced_commands)}",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                f"❌ **Sync failed**: {e}",
                ephemeral=True
            )
