from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

class TestCog(commands.Cog):
    """Minimal test cog to debug loading issues."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
    
    @app_commands.command(name="test_command", description="Test command for debugging")
    async def test_command(self, interaction: discord.Interaction) -> None:
        """Test command."""
        await interaction.response.send_message("Test command works!", ephemeral=True)
