"""Test commands cog for debugging and verification"""
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
import traceback
from typing import Optional
import logging

log = logging.getLogger(__name__)

class TestCommandsCog(commands.Cog):
    """Test commands for verification and self-testing"""
    
    def __init__(self, bot):
        self.bot = bot
        self._test_lock = asyncio.Lock()

    @app_commands.command(name="test_ping", description="Test bot connectivity")
    async def test_ping(self, interaction: discord.Interaction):
        """Simple ping command"""
        await interaction.response.send_message(f"Pong! Latency: {round(self.bot.latency * 1000)}ms")
    
    @app_commands.command(name="test_echo", description="Echo back a message")
    @app_commands.describe(message="Message to echo back")
    async def test_echo(self, interaction: discord.Interaction, message: str):
        """Echo command"""
        await interaction.response.send_message(f"You said: {message}")
    
    @app_commands.command(name="test_userinfo", description="Get user information")
    async def test_userinfo(self, interaction: discord.Interaction):
        """Get user info"""
        user = interaction.user
        embed = discord.Embed(
            title="User Information",
            color=discord.Color.blue()
        )
        embed.add_field(name="Name", value=user.display_name, inline=True)
        embed.add_field(name="ID", value=str(user.id), inline=True)
        embed.add_field(name="Created", value=user.created_at.strftime("%Y-%m-%d"), inline=True)
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="test_serverinfo", description="Get server information")
    async def test_serverinfo(self, interaction: discord.Interaction):
        """Get server info"""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.")
            return
        
        guild = interaction.guild
        embed = discord.Embed(
            title="Server Information",
            color=discord.Color.green()
        )
        embed.add_field(name="Name", value=guild.name, inline=True)
        embed.add_field(name="ID", value=str(guild.id), inline=True)
        embed.add_field(name="Owner", value=guild.owner.display_name if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
        await interaction.response.send_message(embed=embed)
    
    @commands.hybrid_command(name="test_hybrid", description="Test hybrid command functionality")
    @commands.describe(message="Message to echo back")
    async def test_hybrid(self, ctx: commands.Context, *, message: str):
        """Hybrid test command - works with both slash and prefix"""
        if ctx.interaction:
            await ctx.interaction.response.send_message(f"Hybrid echo: {message}")
        else:
            await ctx.send(f"Hybrid echo: {message}")
    
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
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            await self.bot.tree.sync()
            await interaction.followup.send("✅ Commands synced successfully", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to sync: {e}", ephemeral=True)

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(TestCommandsCog(bot))
    log.info("TestCommandsCog loaded")
