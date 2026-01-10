from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

import discord
from discord.ext import commands

from ..services.discord_safety import safe_followup
from ..utils import safe_embed, info_embed, success_embed, error_embed
from ..constants import COLORS

class OverhaulExecutorV2:
    """Enhanced server overhaul with real-time progress and leveling integration."""
    
    def __init__(self, cog: commands.Cog, guild: discord.Guild, config: dict[str, Any]) -> None:
        self.cog = cog
        self.bot = cog.bot
        self.guild = guild
        self.config = config
        self.progress_message: Optional[discord.Message] = None
        self.progress_user: Optional[discord.User] = None
        self.start_time = time.time()
        self.total_steps = 8
        self.current_step = 0
        
    async def run(self) -> str:
        """Run enhanced overhaul with real-time progress updates."""
        try:
            # Initialize progress message
            await self._init_progress_message()
            
            # Step 1: Apply server settings
            await self._update_progress("Applying server settings...", 1)
            await self._apply_server_settings()
            
            # Step 2: Create roles with leveling integration
            await self._update_progress("Creating roles with leveling system...", 2)
            role_map = await self._create_enhanced_roles()
            
            # Step 3: Set role hierarchy
            await self._update_progress("Setting role hierarchy...", 3)
            await self._set_role_hierarchy(role_map)
            
            # Step 4: Create categories and channels
            await self._update_progress("Creating categories and channels...", 4)
            await self._create_categories_and_channels(role_map)
            
                        
            # Step 5: Configure leveling system
            await self._update_progress("Configuring leveling system...", 5)
            await self._setup_leveling_system(role_map)
            
            # Step 6: Configure bot modules
            await self._update_progress("Configuring bot modules...", 6)
            await self._configure_bot_modules()
            
            # Step 7: Setup welcome system
            await self._update_progress("Setting up welcome system...", 7)
            await self._setup_welcome_system()
            
            # Step 8: Final cleanup
            await self._update_progress("Finalizing overhaul...", 8)
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
        embed.add_field(name="Progress", value="0/8 steps completed", inline=True)
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
            embed.add_field(name="Progress", value=f"{step}/8 steps completed", inline=True)
            embed.add_field(name="Time Elapsed", value=elapsed, inline=True)
            
            # Progress bar
            progress_bar = "█" * step + "░" * (8 - step)
            embed.add_field(name="Status", value=f"`{progress_bar}` {step*11:.0f}%", inline=False)
        
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
        embed.add_field(name="Steps Completed", value="8/8", inline=True)
        embed.add_field(name="Status", value="`████████` 100%", inline=False)
        
        try:
            if self.progress_message:
                await self.progress_message.edit(embed=embed)
        except:
            pass
    
    async def _apply_server_settings(self) -> None:
        """Apply server-wide settings."""
        await self.guild.edit(
            name=self.config["server_name"],
            verification_level=getattr(discord.VerificationLevel, self.config["verification_level"], discord.VerificationLevel.high),
            default_notifications=getattr(discord.NotificationLevel, self.config["default_notifications"], discord.NotificationLevel.only_mentions),
            explicit_content_filter=getattr(discord.ExplicitContentFilter, self.config["content_filter"], discord.ExplicitContentFilter.all_members),
            reason="833s Guardian Overhaul V2",
        )
    
    async def _create_enhanced_roles(self) -> dict[str, discord.Role]:
        """Create roles with integrated leveling system."""
        role_map = {}
        
        # Level-based roles with permissions
        level_roles = [
            {"name": "Bronze", "color": "brown", "level": 1, "permissions": ["send_messages", "read_messages"]},
            {"name": "Silver", "color": "greyple", "level": 5, "permissions": ["send_messages", "read_messages", "embed_links"]},
            {"name": "Gold", "color": "gold", "level": 10, "permissions": ["send_messages", "read_messages", "embed_links", "attach_files"]},
            {"name": "Platinum", "color": "white", "level": 25, "permissions": ["send_messages", "read_messages", "embed_links", "attach_files", "add_reactions"]},
            {"name": "Diamond", "color": "cyan", "level": 50, "permissions": ["send_messages", "read_messages", "embed_links", "attach_files", "add_reactions", "external_emojis"]},
        ]
        
        # Create level roles
        for role_data in level_roles:
            color = getattr(discord.Color, role_data["color"], discord.Color.default)()
            role = await self.guild.create_role(
                name=role_data["name"],
                color=color,
                hoist=True,
                reason="833s Guardian Overhaul V2 - Level Role",
            )
            role_map[role_data["name"]] = role
            await asyncio.sleep(0.1)
        
        # Create utility roles
        utility_roles = ["Verified", "Member", "Muted", "VIP"]
        for role_name in utility_roles:
            role = await self.guild.create_role(
                name=role_name,
                color=discord.Color.blue() if role_name != "Muted" else discord.Color.red(),
                reason="833s Guardian Overhaul V2 - Utility Role",
            )
            role_map[role_name] = role
            await asyncio.sleep(0.1)
        
        return role_map
    
    async def _set_role_hierarchy(self, role_map: dict[str, discord.Role]) -> None:
        """Set proper role hierarchy with level roles above utility roles."""
        bot_member = self.guild.me
        top_pos = bot_member.top_role.position
        
        positions = {}
        current_pos = top_pos - 1
        
        # Order: Diamond > Platinum > Gold > Silver > Bronze > VIP > Member > Verified > Muted
        hierarchy_order = ["Diamond", "Platinum", "Gold", "Silver", "Bronze", "VIP", "Member", "Verified", "Muted"]
        
        for role_name in hierarchy_order:
            if role_name in role_map:
                positions[role_map[role_name]] = current_pos
                current_pos -= 1
        
        if positions:
            await self.guild.edit_role_positions(positions=positions, reason="833s Guardian Overhaul V2")
    
    async def _create_categories_and_channels(self, role_map: dict[str, discord.Role]) -> None:
        """Create categories and channels with proper permissions."""
        
        # Main categories
        categories_config = [
            {
                "name": "INFORMATION",
                "channels": [
                    {"name": "rules", "type": "text", "permissions": {"@everyone": "read_only"}},
                    {"name": "announcements", "type": "text", "permissions": {"@everyone": "read_only", "VIP": "full"}},
                    {"name": "events", "type": "text", "permissions": {"@everyone": "read_only", "VIP": "full"}},
                ]
            },
            {
                "name": "GENERAL",
                "channels": [
                    {"name": "general", "type": "text", "permissions": {"Bronze": "full"}},
                    {"name": "commands", "type": "text", "permissions": {"@everyone": "full"}},
                    {"name": "media", "type": "text", "permissions": {"Silver": "full"}},
                ]
            },
            {
                "name": "GAMING",
                "channels": [
                    {"name": "gaming", "type": "text", "permissions": {"Gold": "full"}},
                    {"name": "tournaments", "type": "text", "permissions": {"Platinum": "full"}},
                ]
            },
            {
                "name": "VOICE",
                "channels": [
                    {"name": "General", "type": "voice", "permissions": {"Bronze": "full"}},
                    {"name": "Gaming", "type": "voice", "permissions": {"Gold": "full"}},
                    {"name": "VIP Lounge", "type": "voice", "permissions": {"VIP": "full"}},
                ]
            }
        ]
        
        for cat_config in categories_config:
            category = await self.guild.create_category(
                name=cat_config["name"],
                reason="833s Guardian Overhaul V2"
            )
            
            for chan_config in cat_config["channels"]:
                if chan_config["type"] == "text":
                    await category.create_text_channel(
                        name=chan_config["name"],
                        overwrites=self._create_channel_overwrites(chan_config["permissions"], role_map),
                        reason="833s Guardian Overhaul V2"
                    )
                else:
                    await category.create_voice_channel(
                        name=chan_config["name"],
                        overwrites=self._create_channel_overwrites(chan_config["permissions"], role_map),
                        reason="833s Guardian Overhaul V2"
                    )
                await asyncio.sleep(0.1)
    
    def _create_channel_overwrites(self, permissions: dict[str, str], role_map: dict[str, discord.Role]) -> dict:
        """Create permission overwrites for channels."""
        overwrites = {}
        everyone = self.guild.default_role
        
        # Default everyone permissions
        overwrites[everyone] = discord.PermissionOverwrite(
            view_channel=False,
            send_messages=False,
            connect=False
        )
        
        # Apply role-specific permissions
        for role_name, perm_type in permissions.items():
            if role_name == "@everyone":
                if perm_type == "read_only":
                    overwrites[everyone] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=False,
                        read_message_history=True
                    )
                elif perm_type == "full":
                    overwrites[everyone] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        add_reactions=True
                    )
            elif role_name in role_map:
                if perm_type == "full":
                    overwrites[role_map[role_name]] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        add_reactions=True,
                        embed_links=True,
                        attach_files=True
                    )
        
        return overwrites
    
    async def _setup_leveling_system(self, role_map: dict[str, discord.Role]) -> None:
        """Configure the leveling system with role rewards."""
        # Store level role mappings in bot's database
        level_rewards = {
            1: role_map.get("Bronze"),
            5: role_map.get("Silver"),
            10: role_map.get("Gold"),
            25: role_map.get("Platinum"),
            50: role_map.get("Diamond"),
        }
        
        # Configure level rewards in the levels store
        if hasattr(self.bot, 'levels_store'):
            for level, role in level_rewards.items():
                if role:
                    await self.bot.levels_store.set_role_reward(self.guild.id, level, role.id)
    
    async def _configure_bot_modules(self) -> None:
        """Configure all bot modules with new settings."""
        # Configure starboard
        starboard_channel = discord.utils.get(self.guild.text_channels, name="starboard")
        if starboard_channel and hasattr(self.bot, 'starboard_store'):
            await self.bot.starboard_store.set_starboard_channel(self.guild.id, starboard_channel.id)
        
        # Configure welcome channel
        welcome_channel = discord.utils.get(self.guild.text_channels, name="rules")
        if welcome_channel and hasattr(self.bot, 'guild_store'):
            config = await self.bot.guild_store.get(self.guild.id)
            # Update with new welcome channel
            config.welcome_channel_id = welcome_channel.id
            await self.bot.guild_store.upsert(config)
    
    async def _setup_welcome_system(self) -> None:
        """Setup automated welcome system."""
        welcome_channel = discord.utils.get(self.guild.text_channels, name="rules")
        if not welcome_channel:
            return
        
        # Create welcome message
        embed = discord.Embed(
            title="Welcome to the Server!",
            description="Thank you for joining! Please read the rules and enjoy your stay.",
            color=COLORS["success"]
        )
        
        embed.add_field(name="Rules", value="Check the rules channel for server guidelines.", inline=True)
        embed.add_field(name="Roles", value="Get roles in the reaction-roles channel.", inline=True)
        embed.add_field(name="Level Up", value="Participate to unlock more features!", inline=True)
        
        embed.set_footer(text="Enjoy your stay!")
        
        await welcome_channel.send(embed=embed)
    
    async def _finalize_overhaul(self) -> None:
        """Final cleanup and optimizations."""
        # Set server icon if available
        if "server_icon" in self.config:
            try:
                # This would need actual image data
                pass
            except:
                pass
        
        # Optimize server settings
        await self.guild.edit(
            afk_channel=discord.utils.get(self.guild.voice_channels, name="AFK"),
            afk_timeout=300,
            reason="833s Guardian Overhaul V2 - Finalization"
        )
