from __future__ import annotations

import asyncio
import inspect
import io
import traceback
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Type, Union

import discord
from discord.ext import commands

from .dryrun import dry_run_mode, is_dry_run
from .patch_discord import patch_discord_methods, restore_discord_methods, get_side_effects_log, clear_side_effects_log
from .fakes import FakeContext, FakeInteraction, FakeGuild, FakeTextChannel, FakeVoiceChannel, FakeCategory, FakeRole, FakeMember, FakeUser

# Command test modes
TEST_READONLY = "readonly"
TEST_SANDBOX = "sandbox"
TEST_DESTRUCTIVE = "destructive"

# Default test modes for command patterns
COMMAND_TEST_MODES = {
    # Destructive commands
    "overhaul": TEST_DESTRUCTIVE,
    "guardian_rebuild": TEST_DESTRUCTIVE,
    "guardian_validate": TEST_DESTRUCTIVE,
    "reset": TEST_DESTRUCTIVE,
    "delete": TEST_DESTRUCTIVE,
    "wipe": TEST_DESTRUCTIVE,
    "purge": TEST_READONLY,  # purge is readonly for testing
    "dm_cleanup": TEST_READONLY,
    "dm_cleanup_bulk": TEST_READONLY,
    
    # Admin management (destructive to Discord roles)
    "elevate_admin": TEST_DESTRUCTIVE,
    "revoke_admin": TEST_DESTRUCTIVE,
    
    # Root management (destructive to database)
    "root_request": TEST_DESTRUCTIVE,
    "root_approve": TEST_DESTRUCTIVE,
    "root_reject": TEST_DESTRUCTIVE,
    "root_remove": TEST_DESTRUCTIVE,
    
    # Channel/role creation (sandbox)
    "create": TEST_SANDBOX,
    "setup": TEST_SANDBOX,
    "panel": TEST_SANDBOX,
    
    # Information commands (readonly)
    "help": TEST_READONLY,
    "info": TEST_READONLY,
    "list": TEST_READONLY,
    "show": TEST_READONLY,
    "stats": TEST_READONLY,
    "ping": TEST_READONLY,
    "uptime": TEST_READONLY,
    "rank": TEST_READONLY,
    "leaderboard": TEST_READONLY,
    "balance": TEST_READONLY,
    "rep": TEST_READONLY,
    "achievements": TEST_READONLY,
    "cases": TEST_READONLY,
    "serverinfo": TEST_READONLY,
    "userinfo": TEST_READONLY,
    "config_show": TEST_READONLY,
    "kb": TEST_READONLY,
    "kb_search": TEST_READONLY,
    "levels_settings": TEST_READONLY,
    "levels_reward_list": TEST_READONLY,
    "rr_panel_create": TEST_SANDBOX,
    "starboard_set": TEST_SANDBOX,
    "giveaway_start": TEST_SANDBOX,
    "remind": TEST_READONLY,
    "suggest": TEST_READONLY,
    "warn": TEST_DESTRUCTIVE,
    "timeout": TEST_DESTRUCTIVE,
}

def get_command_test_mode(command_name: str) -> str:
    """Get the test mode for a command based on its name."""
    command_name_lower = command_name.lower()
    
    # Check exact matches first
    if command_name_lower in COMMAND_TEST_MODES:
        return COMMAND_TEST_MODES[command_name_lower]
    
    # Check pattern matches
    for pattern, mode in COMMAND_TEST_MODES.items():
        if pattern in command_name_lower:
            return mode
    
    # Default to readonly for unknown commands
    return TEST_READONLY

class CommandTestResult:
    """Result of testing a single command."""
    
    def __init__(self, command_name: str):
        self.command_name = command_name
        self.status = "SKIP"  # PASS, FAIL, SKIP
        self.error: Optional[Exception] = None
        self.traceback: Optional[str] = None
        self.side_effects: List[Dict[str, Any]] = []
        self.skip_reason: Optional[str] = None
        self.duration: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for reporting."""
        return {
            'command': self.command_name,
            'status': self.status,
            'error': str(self.error) if self.error else None,
            'traceback': self.traceback,
            'side_effects': self.side_effects,
            'skip_reason': self.skip_reason,
            'duration': self.duration
        }

class SelfTestRunner:
    """Runner for executing self-tests on bot commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.results: List[CommandTestResult] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    async def run_dry_test(self) -> str:
        """Run dry test on all commands."""
        self.start_time = time.time()
        self.results.clear()
        
        # Enable dry run mode and patch Discord methods
        with dry_run_mode():
            patch_discord_methods()
            
            try:
                # Test all prefix commands
                await self._test_prefix_commands()
                
                # Test app commands (limited)
                await self._test_app_commands()
                
            finally:
                # Restore original methods
                restore_discord_methods()
                clear_side_effects_log()
        
        self.end_time = time.time()
        return self._generate_report()
    
    async def run_live_test(self, guild: discord.Guild, channel: discord.TextChannel) -> str:
        """Run live test in a specific guild and channel."""
        self.start_time = time.time()
        self.results.clear()
        
        # Create sandbox category
        sandbox_category = None
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            sandbox_category = await guild.create_category(f"__selftest__{timestamp}")
            
            # Test commands with appropriate modes
            await self._test_commands_live(guild, channel, sandbox_category)
            
        finally:
            # Cleanup sandbox
            if sandbox_category:
                try:
                    await sandbox_category.delete()
                except (discord.Forbidden, discord.HTTPException):
                    pass  # Ignore cleanup errors
        
        self.end_time = time.time()
        return self._generate_report()
    
    async def _test_prefix_commands(self) -> None:
        """Test all prefix commands."""
        for command in self.bot.commands:
            if command.hidden:
                continue
            
            result = CommandTestResult(command.name)
            start = time.time()
            
            try:
                # Create fake context
                ctx = self._create_fake_context(command)
                
                # Generate arguments
                args, kwargs = self._generate_command_args(command)
                if args is None:  # Skip if we can't generate args
                    result.skip_reason = "Cannot generate required arguments"
                    self.results.append(result)
                    continue
                
                # Execute command
                await command(ctx, *args, **kwargs)
                result.status = "PASS"
                
            except Exception as e:
                result.status = "FAIL"
                result.error = e
                result.traceback = traceback.format_exc()
            
            finally:
                result.duration = time.time() - start
                result.side_effects = get_side_effects_log().copy()
                clear_side_effects_log()
                self.results.append(result)
    
    async def _test_app_commands(self) -> None:
        """Test app commands (limited)."""
        # Get all app commands from the tree
        for command in self.bot.tree.walk_commands():
            if command.parent:  # Skip subcommands for now
                continue
            
            result = CommandTestResult(command.name)
            start = time.time()
            
            try:
                # Create fake interaction
                interaction = self._create_fake_interaction(command)
                
                # Generate arguments
                args, kwargs = self._generate_app_command_args(command)
                if kwargs is None:  # Skip if we can't generate args
                    result.skip_reason = "Cannot generate required arguments"
                    self.results.append(result)
                    continue
                
                # Execute command
                await command.callback(interaction, **kwargs)
                result.status = "PASS"
                
            except Exception as e:
                result.status = "FAIL"
                result.error = e
                result.traceback = traceback.format_exc()
            
            finally:
                result.duration = time.time() - start
                result.side_effects = get_side_effects_log().copy()
                clear_side_effects_log()
                self.results.append(result)
    
    async def _test_commands_live(self, guild: discord.Guild, channel: discord.TextChannel, sandbox_category: discord.CategoryChannel) -> None:
        """Test commands in live mode with appropriate restrictions."""
        for command in self.bot.commands:
            if command.hidden:
                continue
            
            test_mode = get_command_test_mode(command.name)
            
            # Skip destructive commands in live mode
            if test_mode == TEST_DESTRUCTIVE:
                result = CommandTestResult(command.name)
                result.status = "SKIP"
                result.skip_reason = "Destructive command not run in live mode"
                self.results.append(result)
                continue
            
            result = CommandTestResult(command.name)
            start = time.time()
            
            try:
                # Create real context
                ctx = await self._create_real_context(guild, channel, command)
                
                # Generate arguments
                args, kwargs = self._generate_command_args(command)
                if args is None:
                    result.skip_reason = "Cannot generate required arguments"
                    self.results.append(result)
                    continue
                
                # Modify sandbox commands to use sandbox category
                if test_mode == TEST_SANDBOX:
                    kwargs = self._adapt_for_sandbox(kwargs, sandbox_category)
                
                # Execute command
                await command(ctx, *args, **kwargs)
                result.status = "PASS"
                
            except Exception as e:
                result.status = "FAIL"
                result.error = e
                result.traceback = traceback.format_exc()
            
            finally:
                result.duration = time.time() - start
                self.results.append(result)
    
    def _create_fake_context(self, command: commands.Command) -> FakeContext:
        """Create a fake context for testing."""
        guild = FakeGuild()
        channel = FakeTextChannel()
        member = FakeMember()
        
        # Set up relationships
        member.guild = guild
        channel.guild = guild
        guild.me = member
        
        ctx = FakeContext(self.bot, guild, channel, member)
        ctx.command = command
        return ctx
    
    def _create_fake_interaction(self, command: discord.app_commands.Command) -> FakeInteraction:
        """Create a fake interaction for testing."""
        guild = FakeGuild()
        channel = FakeTextChannel()
        user = FakeUser()
        
        # Set up relationships
        channel.guild = guild
        
        interaction = FakeInteraction(self.bot, guild, channel, user)
        interaction.command = command
        return interaction
    
    async def _create_real_context(self, guild: discord.Guild, channel: discord.TextChannel, command: commands.Command) -> commands.Context:
        """Create a real context for live testing."""
        # Create a fake message
        message = discord.utils.MISSING
        
        # Use the bot's get_context method
        ctx = await self.bot.get_context(message)
        ctx.guild = guild
        ctx.channel = channel
        ctx.author = guild.me
        ctx.command = command
        
        return ctx
    
    def _generate_command_args(self, command: commands.Command) -> Optional[Tuple[tuple, dict]]:
        """Generate arguments for a prefix command."""
        args = []
        kwargs = {}
        
        # Get command signature
        sig = inspect.signature(command.callback)
        
        # Skip self and ctx parameters
        params = list(sig.parameters.values())[2:]  # Skip self and ctx
        
        for param in params:
            if param.annotation == inspect.Parameter.empty:
                annotation = str
            else:
                annotation = param.annotation
            
            # Generate value based on type
            value = self._generate_value_for_type(annotation, param.name)
            
            if value is None:
                return None  # Can't generate required argument
            
            if param.kind == param.POSITIONAL_OR_KEYWORD:
                args.append(value)
            elif param.kind == param.KEYWORD_ONLY:
                kwargs[param.name] = value
        
        return tuple(args), kwargs
    
    def _generate_app_command_args(self, command: discord.app_commands.Command) -> Optional[dict]:
        """Generate arguments for an app command."""
        kwargs = {}
        
        # Get command signature
        sig = inspect.signature(command.callback)
        
        # Skip self and interaction parameters
        params = list(sig.parameters.values())[2:]  # Skip self and interaction
        
        for param in params:
            if param.annotation == inspect.Parameter.empty:
                annotation = str
            else:
                annotation = param.annotation
            
            # Generate value based on type
            value = self._generate_value_for_type(annotation, param.name)
            
            if value is None:
                return None  # Can't generate required argument
            
            kwargs[param.name] = value
        
        return kwargs
    
    def _generate_value_for_type(self, annotation: Type, param_name: str) -> Any:
        """Generate a test value for a given type annotation."""
        # Handle Union types (Python 3.10+) or Optional types
        if hasattr(annotation, '__origin__'):
            if annotation.__origin__ is Union:
                # For Union/Optional, try the first non-None type
                for arg in annotation.__args__:
                    if arg is not type(None):
                        value = self._generate_value_for_type(arg, param_name)
                        if value is not None:
                            return value
                return None
        
        # Handle specific Discord types
        if annotation == discord.Member or annotation == FakeMember:
            return FakeMember()
        elif annotation == discord.User or annotation == FakeUser:
            return FakeUser()
        elif annotation == discord.TextChannel or annotation == FakeTextChannel:
            return FakeTextChannel()
        elif annotation == discord.VoiceChannel or annotation == FakeVoiceChannel:
            return FakeVoiceChannel()
        elif annotation == discord.CategoryChannel or annotation == FakeCategory:
            return FakeCategory()
        elif annotation == discord.Role or annotation == FakeRole:
            return FakeRole()
        elif annotation == discord.Guild or annotation == FakeGuild:
            return FakeGuild()
        
        # Handle basic types
        elif annotation == int:
            return 1
        elif annotation == float:
            return 1.0
        elif annotation == str:
            return "test"
        elif annotation == bool:
            return True
        elif annotation == list:
            return []
        elif annotation == dict:
            return {}
        
        # Handle enums
        elif hasattr(annotation, '__members__'):  # It's an Enum
            return list(annotation.__members__.values())[0]
        
        # Default case - try to create an instance
        try:
            if annotation == inspect.Parameter.empty:
                return "test"
            return annotation()
        except Exception:
            return None
    
    def _adapt_for_sandbox(self, kwargs: dict, sandbox_category: discord.CategoryChannel) -> dict:
        """Adapt command arguments for sandbox testing."""
        # For commands that create channels/roles, modify them to use sandbox
        adapted = kwargs.copy()
        
        # Add category parameter if creating channels
        if 'name' in adapted and any(keyword in adapted for keyword in ['channel', 'text_channel', 'voice_channel']):
            adapted['category'] = sandbox_category
        
        return adapted
    
    def _generate_report(self) -> str:
        """Generate a comprehensive test report."""
        duration = (self.end_time or 0) - (self.start_time or 0)
        
        # Count results
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "PASS")
        failed = sum(1 for r in self.results if r.status == "FAIL")
        skipped = sum(1 for r in self.results if r.status == "SKIP")
        
        # Generate report
        report_lines = [
            "=" * 80,
            "833's GUARDIAN BOT SELF-TEST REPORT",
            "=" * 80,
            f"Generated: {datetime.utcnow().isoformat()}",
            f"Duration: {duration:.2f} seconds",
            f"Total Commands: {total}",
            f"Passed: {passed}",
            f"Failed: {failed}",
            f"Skipped: {skipped}",
            f"Success Rate: {(passed / total * 100):.1f}%" if total > 0 else "N/A",
            "",
            "=" * 80,
            "DETAILED RESULTS",
            "=" * 80,
            ""
        ]
        
        # Add detailed results
        for result in self.results:
            report_lines.extend([
                f"Command: {result.command_name}",
                f"Status: {result.status}",
                f"Duration: {result.duration:.3f}s",
            ])
            
            if result.skip_reason:
                report_lines.append(f"Skip Reason: {result.skip_reason}")
            
            if result.error:
                report_lines.extend([
                    f"Error: {type(result.error).__name__}: {result.error}",
                    "Traceback:",
                    result.traceback[:1000] + "..." if len(result.traceback) > 1000 else result.traceback,
                ])
            
            if result.side_effects:
                report_lines.extend([
                    "Side Effects:",
                ])
                for effect in result.side_effects:
                    report_lines.append(f"  - {effect['method']}({', '.join(map(str, effect['args']))})")
            
            report_lines.extend(["", "-" * 40, ""])
        
        # Add summary
        skip_reasons = {}
        for result in self.results:
            if result.skip_reason:
                skip_reasons[result.skip_reason] = skip_reasons.get(result.skip_reason, 0) + 1
        
        if skip_reasons:
            report_lines.extend([
                "=" * 80,
                "SKIP REASONS SUMMARY",
                "=" * 80,
            ])
            for reason, count in skip_reasons.items():
                report_lines.append(f"{reason}: {count}")
        
        report_lines.extend([
            "=" * 80,
            "END OF REPORT",
            "=" * 80,
        ])
        
        return "\n".join(report_lines)
