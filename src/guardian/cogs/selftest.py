from __future__ import annotations

import asyncio
import io
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..testing.selftest_runner import SelfTestRunner

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
        self._runner = SelfTestRunner(bot)
    
    @app_commands.Group(name="selftest", description="Run self-tests on the bot (Bot owner only)")
    @bot_owner_only()
    async def selftest(self, interaction: discord.Interaction) -> None:
        """Self-test command group."""
        pass  # This is just the group, subcommands will handle the actual logic
    
    @selftest.command(name="dry", description="Run dry-run tests (no Discord mutations)")
    @app_commands.describe(
        include_failures="Whether to include detailed failure information"
    )
    @app_commands.cooldown(1, 300)  # 1 use per 5 minutes
    async def dry(self, interaction: discord.Interaction, include_failures: bool = True) -> None:
        """Run dry-run tests on all commands."""
        # Check if another test is running
        if self._test_lock.locked():
            await interaction.response.send_message(
                "❌ Another self-test is already running. Please wait for it to complete.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        async with self._test_lock:
            try:
                # Run the dry test
                await interaction.followup.send("🧪 Running dry-run tests...", ephemeral=True)
                
                report = await self._runner.run_dry_test()
                
                # Create file attachment
                report_bytes = report.encode('utf-8')
                report_file = discord.File(
                    io.BytesIO(report_bytes),
                    filename=f"selftest_dry_{discord.utils.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
                )
                
                # Send summary
                lines = report.split('\n')
                summary_lines = []
                for line in lines:
                    if line.startswith('Total Commands:') or line.startswith('Passed:') or line.startswith('Failed:') or line.startswith('Skipped:') or line.startswith('Success Rate:'):
                        summary_lines.append(line)
                    if line.startswith('Generated:'):
                        summary_lines.append(line)
                    if line.startswith('Duration:'):
                        summary_lines.append(line)
                    if summary_lines and line.startswith('=' * 80):
                        break
                
                summary = '\n'.join(summary_lines) if summary_lines else "Test completed"
                
                await interaction.followup.send(
                    f"✅ **Dry-run test completed**\n\n```\n{summary}\n```",
                    file=report_file,
                    ephemeral=True
                )
                
            except Exception as e:
                self.bot.log.error(f"Dry-run self-test failed: {e}")
                await interaction.followup.send(
                    f"❌ **Dry-run test failed**: {e}",
                    ephemeral=True
                )
    
    @selftest.command(name="live", description="Run live tests in a test guild (Bot owner only)")
    @app_commands.describe(
        test_guild_id="Optional: Override the TEST_GUILD_ID environment variable"
    )
    @app_commands.cooldown(1, 300)  # 1 use per 5 minutes
    async def live(self, interaction: discord.Interaction, test_guild_id: Optional[str] = None) -> None:
        """Run live tests in a specific guild."""
        # Check if another test is running
        if self._test_lock.locked():
            await interaction.response.send_message(
                "❌ Another self-test is already running. Please wait for it to complete.",
                ephemeral=True
            )
            return
        
        # Get test guild ID
        guild_id = int(test_guild_id) if test_guild_id else None
        if not guild_id:
            guild_id = os.getenv('TEST_GUILD_ID')
            if guild_id:
                try:
                    guild_id = int(guild_id)
                except ValueError:
                    guild_id = None
        
        if not guild_id:
            await interaction.response.send_message(
                "❌ No test guild configured. Set TEST_GUILD_ID environment variable or provide test_guild_id parameter.",
                ephemeral=True
            )
            return
        
        # Get the test guild
        guild = self.bot.get_guild(guild_id)
        if not guild:
            await interaction.response.send_message(
                f"❌ Bot is not in the test guild (ID: {guild_id}). Make sure the bot is a member of the test guild.",
                ephemeral=True
            )
            return
        
        # Check if user is in the test guild
        member = guild.get_member(interaction.user.id)
        if not member:
            await interaction.response.send_message(
                f"❌ You are not a member of the test guild (ID: {guild_id}).",
                ephemeral=True
            )
            return
        
        # Find a suitable channel for testing
        test_channel = None
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                test_channel = channel
                break
        
        if not test_channel:
            await interaction.response.send_message(
                f"❌ No suitable channel found in test guild for sending messages.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        async with self._test_lock:
            try:
                # Run the live test
                await interaction.followup.send(
                    f"🧪 Running live tests in guild **{guild.name}** ({guild.id})...",
                    ephemeral=True
                )
                
                report = await self._runner.run_live_test(guild, test_channel)
                
                # Create file attachment
                report_bytes = report.encode('utf-8')
                report_file = discord.File(
                    io.BytesIO(report_bytes),
                    filename=f"selftest_live_{discord.utils.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
                )
                
                # Send summary
                lines = report.split('\n')
                summary_lines = []
                for line in lines:
                    if line.startswith('Total Commands:') or line.startswith('Passed:') or line.startswith('Failed:') or line.startswith('Skipped:') or line.startswith('Success Rate:'):
                        summary_lines.append(line)
                    if line.startswith('Generated:'):
                        summary_lines.append(line)
                    if line.startswith('Duration:'):
                        summary_lines.append(line)
                    if summary_lines and line.startswith('=' * 80):
                        break
                
                summary = '\n'.join(summary_lines) if summary_lines else "Test completed"
                
                await interaction.followup.send(
                    f"✅ **Live test completed in {guild.name}**\n\n```\n{summary}\n```",
                    file=report_file,
                    ephemeral=True
                )
                
            except Exception as e:
                self.bot.log.error(f"Live self-test failed: {e}")
                await interaction.followup.send(
                    f"❌ **Live test failed**: {e}",
                    ephemeral=True
                )
