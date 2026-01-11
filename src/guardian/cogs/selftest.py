from __future__ import annotations

import asyncio
import io
import traceback
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

class SelfTestCog(commands.Cog):
    """Self-test system for Guardian bot."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self._test_lock = asyncio.Lock()
    
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
    
    @app_commands.command(name="selftest_dry", description="Test all commands for errors (Bot owner only)")
    @app_commands.describe(
        include_tracebacks="Include full error tracebacks in report"
    )
    async def selftest_dry(self, interaction: discord.Interaction, include_tracebacks: bool = False) -> None:
        """Test all commands for potential errors."""
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
                # Test all commands
                results = await self._test_all_commands(include_tracebacks)
                
                # Generate report
                report_lines = [
                    "=" * 80,
                    "833's GUARDIAN BOT COMMAND ERROR TEST REPORT",
                    "=" * 80,
                    f"Generated: {discord.utils.utcnow().isoformat()}",
                    f"Type: Command Error Detection",
                    f"Total Commands: {results['total']}",
                    f"Commands Tested: {results['tested']}",
                    f"Commands Passed: {results['passed']}",
                    f"Commands Failed: {results['failed']}",
                    f"Success Rate: {results['success_rate']:.1f}%",
                    "",
                    "=" * 80,
                    "FAILED COMMANDS",
                    "=" * 80,
                ]
                
                if results['errors']:
                    for error in results['errors']:
                        report_lines.append(f"❌ {error['command']}: {error['error']}")
                        if include_tracebacks and error.get('traceback'):
                            report_lines.append("   Traceback:")
                            for line in error['traceback'].split('\n'):
                                report_lines.append(f"   {line}")
                        report_lines.append("")
                else:
                    report_lines.append("✅ No command errors detected!")
                
                report_lines.extend([
                    "",
                    "=" * 80,
                    "PASSED COMMANDS",
                    "=" * 80,
                ])
                
                if results['passed_commands']:
                    for cmd in results['passed_commands'][:50]:  # Limit to first 50
                        report_lines.append(f"✅ {cmd}")
                    
                    if len(results['passed_commands']) > 50:
                        report_lines.append(f"... and {len(results['passed_commands']) - 50} more commands")
                else:
                    report_lines.append("❌ No commands passed validation")
                
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
                    filename=f"selftest_errors_{discord.utils.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
                )
                
                await interaction.followup.send(
                    f"✅ **Command error test completed**\n\n"
                    f"**Summary:**\n"
                    f"• Total Commands: {results['total']}\n"
                    f"• Commands Tested: {results['tested']}\n"
                    f"• Commands Passed: {results['passed']}\n"
                    f"• Commands Failed: {results['failed']}\n"
                    f"• Success Rate: {results['success_rate']:.1f}%\n"
                    f"• Errors Found: {len(results['errors'])}",
                    file=report_file,
                    ephemeral=True
                )
                
            except Exception as e:
                self.bot.log.error(f"Self-test failed: {e}")
                await interaction.followup.send(
                    f"❌ **Self-test failed**: {e}",
                    ephemeral=True
                )
    
    async def _test_all_commands(self, include_tracebacks: bool) -> dict:
        """Test all commands for potential errors."""
        results = {
            'total': 0,
            'tested': 0,
            'passed': 0,
            'failed': 0,
            'success_rate': 0.0,
            'errors': [],
            'passed_commands': []
        }
        
        try:
            # Test app commands (slash commands)
            app_commands_list = list(self.bot.tree.walk_commands())
            results['total'] = len(app_commands_list)
            
            for cmd in app_commands_list:
                if cmd.parent:  # Skip subcommands for now
                    continue
                
                results['tested'] += 1
                cmd_name = f"/{cmd.name}"
                
                try:
                    # Test 1: Check if command has callback
                    if not hasattr(cmd, 'callback') or not cmd.callback:
                        results['failed'] += 1
                        results['errors'].append({
                            'command': cmd_name,
                            'error': 'Missing callback function',
                            'traceback': None
                        })
                        continue
                    
                    # Test 2: Check if callback is callable
                    if not callable(cmd.callback):
                        results['failed'] += 1
                        results['errors'].append({
                            'command': cmd_name,
                            'error': 'Callback is not callable',
                            'traceback': None
                        })
                        continue
                    
                    # Test 3: Check command signature
                    import inspect
                    sig = inspect.signature(cmd.callback)
                    params = list(sig.parameters.values())
                    
                    # Should have at least 'interaction' parameter
                    if not params or not any(p.name == 'interaction' for p in params):
                        results['failed'] += 1
                        results['errors'].append({
                            'command': cmd_name,
                            'error': 'Missing interaction parameter',
                            'traceback': None
                        })
                        continue
                    
                    # Test 4: Try to create a mock interaction (basic validation)
                    try:
                        # This is a very basic test - just check if the command structure is valid
                        # We don't actually invoke the command to avoid side effects
                        if hasattr(cmd, 'description') and cmd.description:
                            # Command has description - good
                            pass
                        else:
                            results['failed'] += 1
                            results['errors'].append({
                                'command': cmd_name,
                                'error': 'Missing command description',
                                'traceback': None
                            })
                            continue
                    except Exception as e:
                        if include_tracebacks:
                            tb = traceback.format_exc()
                        else:
                            tb = None
                        
                        results['failed'] += 1
                        results['errors'].append({
                            'command': cmd_name,
                            'error': f'Structure validation failed: {str(e)}',
                            'traceback': tb
                        })
                        continue
                    
                    # If we got here, command passed basic validation
                    results['passed'] += 1
                    results['passed_commands'].append(cmd_name)
                    
                except Exception as e:
                    if include_tracebacks:
                        tb = traceback.format_exc()
                    else:
                        tb = None
                    
                    results['failed'] += 1
                    results['errors'].append({
                        'command': cmd_name,
                        'error': f'Validation error: {str(e)}',
                        'traceback': tb
                    })
            
            # Calculate success rate
            if results['tested'] > 0:
                results['success_rate'] = (results['passed'] / results['tested']) * 100
            
        except Exception as e:
            self.bot.log.error(f"Error during command testing: {e}")
            results['errors'].append({
                'command': 'TEST_SYSTEM',
                'error': f'Test system error: {str(e)}',
                'traceback': traceback.format_exc() if include_tracebacks else None
            })
        
        return results
