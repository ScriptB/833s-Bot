from __future__ import annotations

import asyncio
import io
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# from ..testing.selftest_runner import SelfTestRunner

# Bot owner cache
_bot_owner_ids: Optional[set[int]] = None
_bot_owner_cache_time: Optional[float] = None

async def get_application_owner_ids(bot: commands.Bot) -> set[int]:
    """Get the application owner and team member IDs."""
    global _bot_owner_ids, _bot_owner_cache_time
    
    # Cache for 5 minutes
    current_time = asyncio.get_event_loop().time()
    if _bot_owner_ids and _bot_owner_cache_time and (current_time - _bot_owner_cache_time) < 300:
        return _bot_owner_ids
    
    try:
        app_info = await bot.application_info()
        
        if app_info.team:
            # Include all team members
            owner_ids = {member.id for member in app_info.team.members}
        else:
            # Just the owner
            owner_ids = {app_info.owner.id}
        
        _bot_owner_ids = owner_ids
        _bot_owner_cache_time = current_time
        return owner_ids
        
    except Exception as e:
        bot.log.error(f"Failed to get application owner info: {e}")
        return set()

async def is_bot_owner(bot: commands.Bot, user_id: int) -> bool:
    """Check if a user is a bot application owner or team member."""
    owner_ids = await get_application_owner_ids(bot)
    return user_id in owner_ids

def bot_owner_only():
    """Decorator to restrict commands to bot owners only."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not await is_bot_owner(interaction.client, interaction.user.id):
            await interaction.response.send_message(
                "❌ This command is restricted to bot application owners only.",
                ephemeral=True
            )
            return False
        return True
    
    return app_commands.check(predicate)

class SelfTestCog(commands.Cog):
    """Self-test system for the Guardian bot."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self._test_lock = asyncio.Lock()
        # self._runner = SelfTestRunner(bot)
    
    @app_commands.command(name="selftest_dry", description="Run dry-run tests on the bot (Bot owner only)")
    @app_commands.describe(
        include_failures="Whether to include detailed failure information"
    )
    @app_commands.cooldown(1, 300)  # 1 use per 5 minutes
    @bot_owner_only()
    async def selftest_dry(self, interaction: discord.Interaction, include_failures: bool = True) -> None:
        """Run dry-run tests on all commands."""
        await interaction.response.send_message(
            "🧪 Self-test system is temporarily disabled for debugging.",
            ephemeral=True
        )
    
    @app_commands.command(name="selftest_live", description="Run live tests in a test guild (Bot owner only)")
    @app_commands.describe(
        test_guild_id="Optional: Override the TEST_GUILD_ID environment variable"
    )
    @app_commands.cooldown(1, 300)  # 1 use per 5 minutes
    @bot_owner_only()
    async def selftest_live(self, interaction: discord.Interaction, test_guild_id: Optional[str] = None) -> None:
        """Run live tests in a specific guild."""
        await interaction.response.send_message(
            "🧪 Self-test system is temporarily disabled for debugging.",
            ephemeral=True
        )
