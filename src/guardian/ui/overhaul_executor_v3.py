from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import discord
from discord.ext import commands

from ..utils import info_embed, error_embed, success_embed
from ..constants import COLORS


class OverhaulExecutorV3:
    """Simplified and robust server overhaul system."""
    
    def __init__(self, cog: commands.Cog, guild: discord.Guild, config: dict[str, Any]) -> None:
        self.cog = cog
        self.bot = cog.bot
        self.guild = guild
        self.config = config
        self.progress_message: Optional[discord.Message] = None
        self.progress_user: Optional[discord.User] = None
        self.start_time = time.time()
        self.total_steps = 6
        self.current_step = 0
        
    async def run(self) -> str:
        """Run simplified overhaul with real-time progress updates."""
        try:
            # Initialize progress message
            await self._init_progress_message()
            
            # Step 1: Apply server settings
            await self._update_progress("Applying server settings...", 1)
            await self._apply_server_settings()
            
            # Step 2: Create roles
            await self._update_progress("Creating server roles...", 2)
            role_map = await self._create_roles()
            
            # Step 3: Create categories and channels
            await self._update_progress("Creating categories and channels...", 3)
            await self._create_categories_and_channels(role_map)
            
            # Step 4: Setup leveling system
            await self._update_progress("Configuring leveling system...", 4)
            await self._setup_leveling_system(role_map)
            
            # Step 5: Configure bot modules
            await self._update_progress("Configuring bot modules...", 5)
            await self._configure_bot_modules()
            
            # Step 6: Final cleanup
            await self._update_progress("Finalizing overhaul...", 6)
            await self._finalize_overhaul()
            
            # Complete
            elapsed = f"{time.time() - self.start_time:.2f}s"
            await self._complete_progress(elapsed)
            return f"✅ Server overhaul completed in {elapsed}"
            
        except Exception as e:
            error_msg = f"❌ Overhaul failed: {type(e).__name__}: {e}"
            await self._update_progress(error_msg, -1)
            return error_msg
    
    async def _init_progress_message(self) -> None:
        """Initialize the progress message."""
        embed = info_embed("⚙️ Starting Server Overhaul")
        embed.description = "Initializing server rebuild process..."
        embed.add_field(name="Progress", value="0/6 steps completed", inline=True)
        embed.add_field(name="Time Elapsed", value="0.0s", inline=True)
        
        try:
            if self.progress_user:
                self.progress_message = await self.progress_user.send(embed=embed)
            else:
                self.progress_message = await self.cog.bot.get_user(1008255853859721216).send(embed=embed)
        except:
            pass
    
    async def _update_progress(self, message: str, step: int) -> None:
        """Update progress message with current step."""
        self.current_step = step
        elapsed = f"{time.time() - self.start_time:.1f}s"
        
        if step == -1:  # Error
            embed = error_embed("❌ Overhaul Failed")
            embed.description = message
        else:
            embed = info_embed("⚙️ Server Overhaul in Progress")
            embed.description = message
            embed.add_field(name="Progress", value=f"{step}/6 steps completed", inline=True)
            embed.add_field(name="Time Elapsed", value=elapsed, inline=True)
            
            # Progress bar
            progress_bar = "█" * step + "░" * (6 - step)
            embed.add_field(name="Status", value=f"`{progress_bar}` {step*17:.0f}%", inline=False)
        
        try:
            if self.progress_message:
                await self.progress_message.edit(embed=embed)
        except:
            pass
    
    async def _complete_progress(self, elapsed: str) -> None:
        """Mark progress as complete."""
        embed = success_embed("✅ Server Overhaul Complete")
        embed.description = f"Server has been successfully rebuilt!"
        embed.add_field(name="Total Time", value=elapsed, inline=True)
        embed.add_field(name="Steps Completed", value="6/6", inline=True)
        embed.add_field(name="Status", value="`██████` 100%", inline=False)
        
        try:
            if self.progress_message:
                await self.progress_message.edit(embed=embed)
        except:
            pass
    
    async def _apply_server_settings(self) -> None:
        """Apply server-wide settings."""
        await self.guild.edit(
            verification_level=discord.VerificationLevel.high,
            default_notifications=discord.DefaultNotificationLevel.only_mentions,
            content_filter=discord.ContentFilter.all_members,
            reason="833s Guardian Overhaul V3"
        )
    
    async def _create_roles(self) -> dict[str, discord.Role]:
        """Create server roles."""
        role_map = {}
        
        # Basic roles
        roles_to_create = [
            ("Verified", discord.Color.green(), False, False),
            ("Member", discord.Color.dark_green(), False, False),
            ("Bronze", discord.Color.blue(), True, False),
            ("Silver", discord.Color.light_grey(), True, False),
            ("Gold", discord.Color.gold(), True, False),
            ("Platinum", discord.Color.purple(), True, False),
            ("Diamond", discord.Color.dark_blue(), True, False),
            ("VIP", discord.Color.orange(), True, True),
            ("Muted", discord.Color.dark_grey(), False, False),
        ]
        
        for role_name, color, hoist, mentionable in roles_to_create:
            role = discord.utils.get(self.guild.roles, name=role_name)
            if not role:
                role = await self.guild.create_role(
                    name=role_name,
                    color=color,
                    hoist=hoist,
                    mentionable=mentionable,
                    reason="833s Guardian Overhaul V3"
                )
            role_map[role_name] = role
        
        return role_map
    
    async def _create_categories_and_channels(self, role_map: dict[str, discord.Role]) -> None:
        """Create categories and channels."""
        categories_config = [
            {
                "name": "INFORMATION",
                "channels": [
                    {"name": "rules", "type": "text"},
                    {"name": "announcements", "type": "text"},
                ]
            },
            {
                "name": "GENERAL",
                "channels": [
                    {"name": "general", "type": "text"},
                    {"name": "commands", "type": "text"},
                ]
            },
            {
                "name": "VOICE",
                "channels": [
                    {"name": "General", "type": "voice"},
                    {"name": "AFK", "type": "voice"},
                ]
            }
        ]
        
        for cat_config in categories_config:
            category = discord.utils.get(self.guild.categories, name=cat_config["name"])
            if not category:
                category = await self.guild.create_category(
                    name=cat_config["name"],
                    reason="833s Guardian Overhaul V3"
                )
            
            for channel_config in cat_config["channels"]:
                if channel_config["type"] == "text":
                    await category.create_text_channel(
                        name=channel_config["name"],
                        reason="833s Guardian Overhaul V3"
                    )
                else:
                    await category.create_voice_channel(
                        name=channel_config["name"],
                        reason="833s Guardian Overhaul V3"
                    )
    
    async def _setup_leveling_system(self, role_map: dict[str, discord.Role]) -> None:
        """Configure leveling system with role rewards."""
        if not hasattr(self.bot, 'levels_store'):
            return
            
        level_rewards = {
            1: role_map.get("Bronze"),
            5: role_map.get("Silver"),
            10: role_map.get("Gold"),
            25: role_map.get("Platinum"),
            50: role_map.get("Diamond"),
        }
        
        for level, role in level_rewards.items():
            if role:
                await self.bot.levels_store.set_role_reward(self.guild.id, level, role.id)
    
    async def _configure_bot_modules(self) -> None:
        """Configure bot modules."""
        # Configure welcome channel
        welcome_channel = discord.utils.get(self.guild.text_channels, name="rules")
        if welcome_channel and hasattr(self.bot, 'guild_store'):
            config = await self.bot.guild_store.get(self.guild.id)
            config.welcome_channel_id = welcome_channel.id
            await self.bot.guild_store.upsert(config)
    
    async def _finalize_overhaul(self) -> None:
        """Final cleanup and optimizations."""
        # Set server icon if available
        if "server_icon" in self.config:
            try:
                await self.guild.edit(icon=self.config["server_icon"])
            except:
                pass
