from __future__ import annotations

import asyncio
import io
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

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
    
    @app_commands.command(name="selftest_dry", description="Run dry-run tests on all commands (Bot owner only)")
    @app_commands.describe(
        include_failures="Whether to include detailed failure information"
    )
    @app_commands.cooldown(1, 300)  # 1 use per 5 minutes
    @bot_owner_only()
    async def selftest_dry(self, interaction: discord.Interaction, include_failures: bool = True) -> None:
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
                # Basic command testing
                commands_tested = 0
                commands_passed = 0
                commands_failed = 0
                errors = []
                
                # Test basic bot commands
                all_commands = list(self.bot.commands)
                app_commands_list = list(self.bot.tree.walk_commands())
                
                # Test prefix commands
                for cmd in all_commands:
                    if cmd.hidden:
                        continue
                    
                    commands_tested += 1
                    try:
                        # Basic validation - just check if command exists and has callback
                        if cmd.callback:
                            commands_passed += 1
                        else:
                            commands_failed += 1
                            errors.append(f"Command {cmd.name} has no callback")
                    except Exception as e:
                        commands_failed += 1
                        errors.append(f"Command {cmd.name}: {str(e)}")
                
                # Test app commands
                for cmd in app_commands_list:
                    if cmd.parent:  # Skip subcommands for now
                        continue
                    
                    commands_tested += 1
                    try:
                        # Basic validation - just check if command exists and has callback
                        if hasattr(cmd, 'callback') and cmd.callback:
                            commands_passed += 1
                        else:
                            commands_failed += 1
                            errors.append(f"App command {cmd.name} has no callback")
                    except Exception as e:
                        commands_failed += 1
                        errors.append(f"App command {cmd.name}: {str(e)}")
                
                # Generate report
                success_rate = (commands_passed / commands_tested * 100) if commands_tested > 0 else 0
                
                report_lines = [
                    "=" * 80,
                    "833's GUARDIAN BOT SELF-TEST REPORT",
                    "=" * 80,
                    f"Generated: {discord.utils.utcnow().isoformat()}",
                    f"Type: Basic Command Validation",
                    f"Total Commands: {commands_tested}",
                    f"Passed: {commands_passed}",
                    f"Failed: {commands_failed}",
                    f"Success Rate: {success_rate:.1f}%",
                    "",
                    "=" * 80,
                    "DETAILED RESULTS",
                    "=" * 80,
                ]
                
                if errors:
                    report_lines.extend([
                        "ERRORS FOUND:",
                        ""
                    ])
                    for error in errors[:20]:  # Limit to first 20 errors
                        report_lines.append(f"• {error}")
                    
                    if len(errors) > 20:
                        report_lines.append(f"... and {len(errors) - 20} more errors")
                
                report_lines.extend([
                    "",
                    "=" * 80,
                    "END OF REPORT",
                    "=" * 80,
                ])
                
                report = "\n".join(report_lines)
                
                # Create file attachment
                report_bytes = report.encode('utf-8')
                report_file = discord.File(
                    io.BytesIO(report_bytes),
                    filename=f"selftest_basic_{discord.utils.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
                )
                
                await interaction.followup.send(
                    f"✅ **Basic self-test completed**\n\n"
                    f"**Summary:**\n"
                    f"• Total Commands: {commands_tested}\n"
                    f"• Passed: {commands_passed}\n"
                    f"• Failed: {commands_failed}\n"
                    f"• Success Rate: {success_rate:.1f}%\n"
                    f"• Errors Found: {len(errors)}",
                    file=report_file,
                    ephemeral=True
                )
                
            except Exception as e:
                self.bot.log.error(f"Self-test failed: {e}")
                await interaction.followup.send(
                    f"❌ **Self-test failed**: {e}",
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
                # Basic live testing - test bot permissions and basic functionality
                tests_passed = 0
                tests_failed = 0
                errors = []
                
                # Test bot permissions
                try:
                    bot_member = guild.me
                    if bot_member.guild_permissions.send_messages:
                        tests_passed += 1
                        await test_channel.send("🧪 Self-test message - bot permissions test")
                    else:
                        tests_failed += 1
                        errors.append("Bot lacks send_messages permission")
                except Exception as e:
                    tests_failed += 1
                    errors.append(f"Permission test failed: {str(e)}")
                
                # Test basic bot functionality
                try:
                    # Test bot can see channels
                    channel_count = len(guild.text_channels)
                    if channel_count > 0:
                        tests_passed += 1
                    else:
                        tests_failed += 1
                        errors.append("No text channels found in guild")
                except Exception as e:
                    tests_failed += 1
                    errors.append(f"Channel test failed: {str(e)}")
                
                # Test bot can see members
                try:
                    member_count = guild.member_count
                    if member_count > 0:
                        tests_passed += 1
                    else:
                        tests_failed += 1
                        errors.append("No members found in guild")
                except Exception as e:
                    tests_failed += 1
                    errors.append(f"Member test failed: {str(e)}")
                
                # Generate report
                total_tests = tests_passed + tests_failed
                success_rate = (tests_passed / total_tests * 100) if total_tests > 0 else 0
                
                report_lines = [
                    "=" * 80,
                    "833's GUARDIAN BOT LIVE SELF-TEST REPORT",
                    "=" * 80,
                    f"Generated: {discord.utils.utcnow().isoformat()}",
                    f"Guild: {guild.name} ({guild.id})",
                    f"Type: Live Permission Tests",
                    f"Total Tests: {total_tests}",
                    f"Passed: {tests_passed}",
                    f"Failed: {tests_failed}",
                    f"Success Rate: {success_rate:.1f}%",
                    "",
                    "=" * 80,
                    "DETAILED RESULTS",
                    "=" * 80,
                ]
                
                if errors:
                    report_lines.extend([
                        "ERRORS FOUND:",
                        ""
                    ])
                    for error in errors:
                        report_lines.append(f"• {error}")
                
                report_lines.extend([
                    "",
                    "=" * 80,
                    "END OF REPORT",
                    "=" * 80,
                ])
                
                report = "\n".join(report_lines)
                
                # Create file attachment
                report_bytes = report.encode('utf-8')
                report_file = discord.File(
                    io.BytesIO(report_bytes),
                    filename=f"selftest_live_{discord.utils.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
                )
                
                await interaction.followup.send(
                    f"✅ **Live self-test completed in {guild.name}**\n\n"
                    f"**Summary:**\n"
                    f"• Total Tests: {total_tests}\n"
                    f"• Passed: {tests_passed}\n"
                    f"• Failed: {tests_failed}\n"
                    f"• Success Rate: {success_rate:.1f}%\n"
                    f"• Errors Found: {len(errors)}",
                    file=report_file,
                    ephemeral=True
                )
                
            except Exception as e:
                self.bot.log.error(f"Live self-test failed: {e}")
                await interaction.followup.send(
                    f"❌ **Live self-test failed**: {e}",
                    ephemeral=True
                )
