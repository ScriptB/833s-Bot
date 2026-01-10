from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import discord
from discord.ext import commands
from dataclasses import replace

from ..utils import info_embed, error_embed, success_embed
from ..constants import COLORS

log = logging.getLogger("guardian.overhaul_executor_v3")

# Runtime debugging - verify LevelsStore has required methods
try:
    from ..services.levels_store import LevelsStore
    log.info(f"LevelsStore loaded from: {LevelsStore.__module__}")
    log.info(f"LevelsStore has set_role_reward: {hasattr(LevelsStore, 'set_role_reward')}")
except Exception as e:
    log.error(f"Failed to import LevelsStore: {e}")


class OverhaulExecutorV3:
    """Professional-grade server overhaul with complete rebuild functionality."""
    
    def __init__(self, cog: commands.Cog, guild: discord.Guild, config: dict[str, Any]) -> None:
        self.cog = cog
        self.bot = cog.bot
        self.guild = guild
        self.config = config
        self.progress_message: Optional[discord.Message] = None
        self.start_time = time.time()
        self.current_step = 0
        
    async def run(self) -> str:
        """Run professional server overhaul with complete rebuild."""
        log.info(f"Starting professional overhaul for guild {self.guild.name} (ID: {self.guild.id})")
        
        try:
            # Initialize progress message
            await self._init_progress_message()
            
            # Phase 1: Full Server Wipe
            log.info("Phase 1: Full server wipe")
            await self._update_progress("Phase 1: Full server wipe...", 1)
            await self._full_server_wipe()
            log.info("Server wipe completed successfully")
            
            # Phase 2: Apply Server Settings
            log.info("Phase 2: Apply server settings")
            await self._update_progress("Phase 2: Apply server settings...", 2)
            await self._apply_server_settings()
            log.info("Server settings applied successfully")
            
            # Phase 3: Create Professional Role System
            log.info("Phase 3: Create professional role system")
            await self._update_progress("Phase 3: Create professional role system...", 3)
            role_map = await self._create_professional_role_system()
            log.info(f"Created {len(role_map)} roles successfully")
            
            # Phase 4: Role-Driven Category System
            log.info("Phase 4: Create role-driven category system")
            await self._update_progress("Phase 4: Create role-driven category system...", 4)
            await self._create_role_driven_categories(role_map)
            log.info("Category system created successfully")
            
            # Phase 5: Correct Permission Overwrites
            log.info("Phase 5: Apply correct permission overwrites")
            await self._update_progress("Phase 5: Apply correct permission overwrites...", 5)
            await self._apply_permission_overwrites(role_map)
            log.info("Permission overwrites applied successfully")
            
            # Phase 6: Setup Leveling System
            log.info("Phase 6: Setup leveling system")
            await self._update_progress("Phase 6: Setup leveling system...", 6)
            await self._setup_leveling_system(role_map)
            log.info("Leveling system configured successfully")
            
            # Phase 7: Configure Bot Modules
            log.info("Phase 7: Configure bot modules")
            await self._update_progress("Phase 7: Configure bot modules...", 7)
            await self._configure_bot_modules()
            log.info("Bot modules configured successfully")
            
            # Phase 8: Finalize Overhaul
            log.info("Phase 8: Finalize overhaul")
            await self._update_progress("Phase 8: Finalize overhaul...", 8)
            await self._finalize_overhaul()
            log.info("Overhaul finalized successfully")
            
            # Complete
            elapsed = f"{time.time() - self.start_time:.2f}s"
            await self._complete_progress(elapsed)
            success_msg = f"✅ Professional server overhaul completed in {elapsed}"
            log.info(f"Professional overhaul completed successfully for guild {self.guild.name}")
            return success_msg
            
        except discord.Forbidden as e:
            error_msg = f"❌ Overhaul failed: Missing permissions - {e}"
            log.error(f"Permission error during overhaul: {e}")
            await self._update_progress(error_msg, -1)
            return error_msg
        except discord.HTTPException as e:
            error_msg = f"❌ Overhaul failed: Discord API error - {e}"
            log.error(f"Discord API error during overhaul: {e}")
            await self._update_progress(error_msg, -1)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Overhaul failed: {type(e).__name__}: {e}"
            log.error(f"Unexpected error during overhaul: {e}", exc_info=True)
            await self._update_progress(error_msg, -1)
            return error_msg
    
    async def _init_progress_message(self) -> None:
        """Initialize progress message."""
        embed = info_embed("🔥 Professional Server Overhaul")
        embed.description = "Starting complete server rebuild..."
        embed.add_field(name="Progress", value="`░░░░░░░░` 0%", inline=False)
        embed.add_field(name="Current Phase", value="Initializing...", inline=True)
        embed.add_field(name="Time Elapsed", value="0s", inline=True)
        
        try:
            self.progress_message = await self.config["interaction_channel"].send(embed=embed)
        except:
            pass
    
    async def _update_progress(self, phase: str, step: int) -> None:
        """Update progress message."""
        self.current_step = step
        elapsed = f"{time.time() - self.start_time:.1f}s"
        progress_bars = [
            "`████████` 100%",  # Step 1
            "`███████░` 87%",   # Step 2
            "`██████░░` 75%",   # Step 3
            "`█████░░░` 62%",   # Step 4
            "`████░░░░` 50%",   # Step 5
            "`███░░░░░` 37%",   # Step 6
            "`██░░░░░░` 25%",   # Step 7
            "`█░░░░░░░` 12%",   # Step 8
        ]
        
        progress_bar = progress_bars[min(step - 1, len(progress_bars) - 1)]
        
        embed = info_embed("🔥 Professional Server Overhaul")
        embed.description = f"**{phase}**"
        embed.add_field(name="Progress", value=progress_bar, inline=False)
        embed.add_field(name="Current Phase", value=f"Phase {step}/8", inline=True)
        embed.add_field(name="Time Elapsed", value=elapsed, inline=True)
        
        try:
            if self.progress_message:
                await self.progress_message.edit(embed=embed)
        except:
            pass
    
    async def _complete_progress(self, elapsed: str) -> None:
        """Mark progress as complete."""
        embed = success_embed("✅ Professional Server Overhaul Complete")
        embed.description = f"Server has been professionally rebuilt!"
        embed.add_field(name="Total Time", value=elapsed, inline=True)
        embed.add_field(name="Phases Completed", value="8/8", inline=True)
        embed.add_field(name="Status", value="`████████` 100%", inline=False)
        
        try:
            if self.progress_message:
                await self.progress_message.edit(embed=embed)
        except:
            pass
    
    async def _full_server_wipe(self) -> None:
        """Phase 1: Delete everything legally deletable."""
        bot_role = self.guild.me.top_role
        
        # Delete all categories and channels
        for category in self.guild.categories:
            try:
                log.info(f"Deleting category: {category.name} (ID: {category.id})")
                await category.delete(reason="Professional Overhaul - Full Wipe")
            except discord.Forbidden:
                log.warning(f"Cannot delete category {category.name} - permission denied")
            except discord.HTTPException as e:
                log.warning(f"Failed to delete category {category.name}: {e}")
            except Exception as e:
                log.error(f"Unexpected error deleting category {category.name}: {e}")
        
        # Delete standalone channels
        for channel in self.guild.channels:
            if channel.category is None:
                try:
                    log.info(f"Deleting standalone channel: {channel.name} (ID: {channel.id})")
                    await channel.delete(reason="Professional Overhaul - Full Wipe")
                except discord.Forbidden:
                    log.warning(f"Cannot delete channel {channel.name} - permission denied")
                except discord.HTTPException as e:
                    log.warning(f"Failed to delete channel {channel.name}: {e}")
                except Exception as e:
                    log.error(f"Unexpected error deleting channel {channel.name}: {e}")
        
        # Delete all roles except protected ones
        roles_to_delete = []
        for role in self.guild.roles:
            # Skip @everyone
            if role.name == "@everyone":
                continue
            
            # Skip roles higher than bot's role
            if role >= bot_role:
                continue
            
            # Skip managed roles
            if role.managed:
                continue
            
            roles_to_delete.append(role)
        
        # Sort by position (lowest to highest)
        roles_to_delete.sort(key=lambda r: r.position)
        
        for role in roles_to_delete:
            try:
                log.info(f"Deleting role: {role.name} (ID: {role.id})")
                await role.delete(reason="Professional Overhaul - Full Wipe")
            except discord.Forbidden:
                log.warning(f"Cannot delete role {role.name} - permission denied")
            except discord.HTTPException as e:
                log.warning(f"Failed to delete role {role.name}: {e}")
            except Exception as e:
                log.error(f"Unexpected error deleting role {role.name}: {e}")
        
        log.info("Full server wipe completed")
    
    async def _apply_server_settings(self) -> None:
        """Phase 2: Apply server settings with correct API."""
        await self.guild.edit(
            verification_level=discord.VerificationLevel.high,
            default_notifications=discord.NotificationLevel.only_mentions,
            explicit_content_filter=discord.ExplicitContentFilter.all_members,
            reason="Professional Overhaul - Server Settings"
        )
    
    async def _create_professional_role_system(self) -> dict[str, discord.Role]:
        """Phase 3: Create clean, professional role system."""
        role_map = {}
        
        # Define role hierarchy (top to bottom)
        role_definitions = [
            ("Owner", discord.Color.red(), True, ["administrator"]),
            ("Admin", discord.Color.orange(), True, ["administrator"]),
            ("Moderator", discord.Color.gold(), True, ["kick_members", "ban_members", "manage_channels", "manage_messages", "manage_roles"]),
            ("Support", discord.Color.blue(), True, ["manage_messages"]),
            ("Bots", discord.Color.purple(), True, ["manage_channels", "manage_roles", "manage_messages"]),
            ("Verified", discord.Color.green(), False, []),
            ("Member", discord.Color.dark_grey(), False, []),
            ("Snakes", discord.Color.dark_green(), False, []),
            ("Coding", discord.Color.dark_blue(), False, []),
            ("Gaming", discord.Color.dark_purple(), False, []),
        ]
        
        # Create roles in order (highest to lowest position)
        for role_name, color, hoist, permissions in role_definitions:
            try:
                role = discord.utils.get(self.guild.roles, name=role_name)
                if not role:
                    log.info(f"Creating role: {role_name}")
                    role = await self.guild.create_role(
                        name=role_name,
                        color=color,
                        hoist=hoist,
                        permissions=discord.Permissions(**{perm: True for perm in permissions}) if permissions else discord.Permissions.none(),
                        reason="Professional Overhaul - Role System"
                    )
                    log.info(f"Successfully created role: {role_name} (ID: {role.id})")
                else:
                    log.info(f"Role already exists: {role_name} (ID: {role.id})")
                
                role_map[role_name] = role
                
            except discord.Forbidden as e:
                log.error(f"Failed to create role {role_name}: Missing permissions - {e}")
                raise
            except discord.HTTPException as e:
                log.error(f"Failed to create role {role_name}: Discord API error - {e}")
                raise
            except Exception as e:
                log.error(f"Unexpected error creating role {role_name}: {e}", exc_info=True)
                raise
        
        log.info("Professional role system created successfully")
        return role_map
    
    async def _create_role_driven_categories(self, role_map: dict[str, discord.Role]) -> None:
        """Phase 4: Create role-driven category system."""
        
        # Define category structure
        category_definitions = [
            {
                "name": "START HERE",
                "roles": [],  # @everyone
                "channels": [
                    {"name": "welcome", "type": "text"},
                    {"name": "rules", "type": "text"},
                    {"name": "announcements", "type": "text", "write_restricted": True},
                ]
            },
            {
                "name": "COMMUNITY",
                "roles": ["Verified", "Member"],
                "channels": [
                    {"name": "chat", "type": "text"},
                    {"name": "media", "type": "text"},
                    {"name": "introductions", "type": "text"},
                ]
            },
            {
                "name": "CODING LAB",
                "roles": ["Coding"] + ["Owner", "Admin", "Moderator", "Support"],
                "channels": [
                    {"name": "dev-chat", "type": "text"},
                    {"name": "snippets", "type": "text"},
                    {"name": "releases", "type": "text"},
                ]
            },
            {
                "name": "SNAKES & PETS",
                "roles": ["Snakes"] + ["Owner", "Admin", "Moderator", "Support"],
                "channels": [
                    {"name": "snake-care", "type": "text"},
                    {"name": "photos", "type": "text"},
                ]
            },
            {
                "name": "GAMING",
                "roles": ["Gaming"] + ["Owner", "Admin", "Moderator", "Support"],
                "channels": [
                    {"name": "game-chat", "type": "text"},
                    {"name": "roblox", "type": "text"},
                    {"name": "minecraft", "type": "text"},
                ]
            },
            {
                "name": "SUPPORT",
                "roles": ["Verified", "Member"],
                "channels": [
                    {"name": "help", "type": "text"},
                    {"name": "tickets", "type": "text"},
                ]
            },
            {
                "name": "STAFF",
                "roles": ["Owner", "Admin", "Moderator", "Support"],
                "channels": [
                    {"name": "staff-chat", "type": "text"},
                    {"name": "mod-logs", "type": "text"},
                ]
            },
            {
                "name": "VOICE",
                "roles": ["Verified", "Member"],
                "channels": [
                    {"name": "Hangout", "type": "voice"},
                    {"name": "Gaming VC", "type": "voice"},
                ]
            },
        ]
        
        # Create categories and channels
        for cat_def in category_definitions:
            try:
                # Create category
                category = await self.guild.create_category(
                    name=cat_def["name"],
                    reason="Professional Overhaul - Category System"
                )
                log.info(f"Created category: {cat_def['name']} (ID: {category.id})")
                
                # Set category permissions (deny @everyone, allow specific roles)
                allowed_roles = [role_map[role_name] for role_name in cat_def["roles"] if role_name in role_map]
                
                overwrites = {
                    self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                }
                
                for role in allowed_roles:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True)
                
                await category.edit(overwrites=overwrites, reason="Professional Overhaul - Category Permissions")
                
                # Create channels in category
                for channel_def in cat_def["channels"]:
                    if channel_def["type"] == "text":
                        channel = await category.create_text_channel(
                            name=channel_def["name"],
                            reason="Professional Overhaul - Channel Creation"
                        )
                    else:
                        channel = await category.create_voice_channel(
                            name=channel_def["name"],
                            reason="Professional Overhaul - Channel Creation"
                        )
                    
                    log.info(f"Created channel: {channel_def['name']} in {cat_def['name']} (ID: {channel.id})")
                    
                    # Apply write restriction for announcements
                    if channel_def.get("write_restricted"):
                        staff_roles = [role_map["Owner"], role_map["Admin"], role_map["Moderator"], role_map["Support"]]
                        write_overwrites = {
                            self.guild.default_role: discord.PermissionOverwrite(send_messages=False),
                        }
                        for role in staff_roles:
                            write_overwrites[role] = discord.PermissionOverwrite(send_messages=True)
                        await channel.edit(overwrites=write_overwrites, reason="Professional Overhaul - Write Restrictions")
                        
            except discord.Forbidden as e:
                log.error(f"Failed to create category {cat_def['name']}: Missing permissions - {e}")
                raise
            except discord.HTTPException as e:
                log.error(f"Failed to create category {cat_def['name']}: Discord API error - {e}")
                raise
            except Exception as e:
                log.error(f"Unexpected error creating category {cat_def['name']}: {e}", exc_info=True)
                raise
        
        log.info("Role-driven category system created successfully")
    
    async def _apply_permission_overwrites(self, role_map: dict[str, discord.Role]) -> None:
        """Phase 5: Apply correct permission overwrites to all categories."""
        # This is handled in _create_role_driven_categories, but keeping for completeness
        log.info("Permission overwrites already applied during category creation")
    
    async def _setup_leveling_system(self, role_map: dict[str, discord.Role]) -> None:
        """Phase 6: Setup leveling system with role rewards."""
        if not hasattr(self.bot, 'levels_store'):
            log.warning("Levels store not available - skipping leveling system setup")
            return
        
        # Debug: Verify levels_store has set_role_reward method
        if not hasattr(self.bot.levels_store, 'set_role_reward'):
            log.error("Levels store exists but missing set_role_reward method")
            return
            
        log.info("Setting up leveling system with role rewards")
        log.info(f"Levels store type: {type(self.bot.levels_store)}")
        log.info(f"Levels store has set_role_reward: {hasattr(self.bot.levels_store, 'set_role_reward')}")
        
        # Map levels to roles (using professional role system)
        level_rewards = {
            5: role_map.get("Member"),
            10: role_map.get("Support"),
            25: role_map.get("Moderator"),
            50: role_map.get("Admin"),
        }
        
        for level, role in level_rewards.items():
            if role:
                try:
                    await self.bot.levels_store.set_role_reward(self.guild.id, level, role.id)
                    log.info(f"Set level reward: Level {level} -> Role {role.name} (ID: {role.id})")
                except Exception as e:
                    log.error(f"Failed to set level reward for level {level}: {e}", exc_info=True)
            else:
                log.warning(f"Role not found for level {level} - skipping reward setup")
        
        log.info("Leveling system setup completed")
    
    async def _configure_bot_modules(self) -> None:
        """Phase 7: Configure bot modules."""
        try:
            # Configure welcome channel
            welcome_channel = discord.utils.get(self.guild.text_channels, name="welcome")
            if welcome_channel and hasattr(self.bot, 'guild_store'):
                log.info(f"Configuring welcome channel: {welcome_channel.name} (ID: {welcome_channel.id})")
                config = await self.bot.guild_store.get(self.guild.id)
                config.welcome_channel_id = welcome_channel.id
                await self.bot.guild_store.upsert(config)
                log.info("Welcome channel configured successfully")
            else:
                if welcome_channel:
                    log.warning("Welcome channel found but guild store not available")
                else:
                    log.warning("Welcome channel not found - skipping configuration")
                    
        except Exception as e:
            log.error(f"Failed to configure bot modules: {e}", exc_info=True)
            # Don't raise here - this is not critical for overhaul completion
    
    async def _finalize_overhaul(self) -> None:
        """Phase 8: Finalize overhaul."""
        log.info("Professional server overhaul finalized successfully")
