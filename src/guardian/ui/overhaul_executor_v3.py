from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import discord
from discord.ext import commands

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
        log.info(f"Starting overhaul for guild {self.guild.name} (ID: {self.guild.id})")
        
        try:
            # Initialize progress message
            await self._init_progress_message()
            
            # Step 1: Clean up existing channels and categories
            log.info("Step 1: Cleaning up existing channels and categories")
            await self._update_progress("Cleaning up existing channels and categories...", 1)
            await self._cleanup_existing_content()
            log.info("Existing content cleaned up successfully")
            
            # Step 2: Clean up existing roles
            log.info("Step 2: Cleaning up existing roles")
            await self._update_progress("Cleaning up existing roles...", 2)
            await self._cleanup_existing_roles()
            log.info("Existing roles cleaned up successfully")
            
            # Step 3: Apply server settings
            log.info("Step 3: Applying server settings")
            await self._update_progress("Applying server settings...", 3)
            await self._apply_server_settings()
            log.info("Server settings applied successfully")
            
            # Step 4: Create roles
            log.info("Step 4: Creating server roles")
            await self._update_progress("Creating server roles...", 4)
            role_map = await self._create_roles()
            log.info(f"Created {len(role_map)} roles successfully")
            
            # Step 5: Create categories and channels
            log.info("Step 5: Creating categories and channels")
            await self._update_progress("Creating categories and channels...", 5)
            await self._create_categories_and_channels(role_map)
            log.info("Categories and channels created successfully")
            
            # Step 6: Setup leveling system
            log.info("Step 6: Configuring leveling system")
            await self._update_progress("Configuring leveling system...", 6)
            await self._setup_leveling_system(role_map)
            log.info("Leveling system configured successfully")
            
            # Step 7: Configure bot modules
            log.info("Step 7: Configuring bot modules")
            await self._update_progress("Configuring bot modules...", 7)
            await self._configure_bot_modules()
            log.info("Bot modules configured successfully")
            
            # Step 8: Final cleanup
            log.info("Step 8: Finalizing overhaul")
            await self._update_progress("Finalizing overhaul...", 8)
            await self._finalize_overhaul()
            log.info("Overhaul finalized successfully")
            
            # Complete
            elapsed = f"{time.time() - self.start_time:.2f}s"
            await self._complete_progress(elapsed)
            success_msg = f"✅ Server overhaul completed in {elapsed}"
            log.info(f"Overhaul completed successfully for guild {self.guild.name}")
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
        embed.add_field(name="Steps Completed", value="8/8", inline=True)
        embed.add_field(name="Status", value="`████████` 100%", inline=False)
        
        try:
            if self.progress_message:
                await self.progress_message.edit(embed=embed)
        except:
            pass
    
    async def _cleanup_existing_content(self) -> None:
        """Delete existing channels and categories (except protected ones)."""
        # Protected channels that should not be deleted
        protected_channel_names = {"general", "rules"} if self.guild.me.guild_permissions.administrator else set()
        
        # Delete all categories and their channels (except protected)
        for category in self.guild.categories:
            try:
                # Check if category contains protected channels
                has_protected = any(channel.name.lower() in protected_channel_names for channel in category.channels)
                
                if not has_protected:
                    log.info(f"Deleting category: {category.name} (ID: {category.id})")
                    await category.delete(reason="833s Guardian Overhaul V3 - Cleanup")
                else:
                    # Delete non-protected channels in this category
                    for channel in category.channels:
                        if channel.name.lower() not in protected_channel_names:
                            log.info(f"Deleting channel: {channel.name} (ID: {channel.id})")
                            await channel.delete(reason="833s Guardian Overhaul V3 - Cleanup")
                            
            except discord.Forbidden as e:
                log.error(f"Failed to delete category {category.name}: Missing permissions - {e}")
                raise
            except discord.HTTPException as e:
                log.error(f"Failed to delete category {category.name}: Discord API error - {e}")
                raise
            except Exception as e:
                log.error(f"Unexpected error deleting category {category.name}: {e}", exc_info=True)
                raise
        
        # Delete standalone channels (not in categories)
        for channel in self.guild.channels:
            if channel.category is None and channel.name.lower() not in protected_channel_names:
                try:
                    log.info(f"Deleting standalone channel: {channel.name} (ID: {channel.id})")
                    await channel.delete(reason="833s Guardian Overhaul V3 - Cleanup")
                except discord.Forbidden as e:
                    log.error(f"Failed to delete channel {channel.name}: Missing permissions - {e}")
                    raise
                except discord.HTTPException as e:
                    log.error(f"Failed to delete channel {channel.name}: Discord API error - {e}")
                    raise
                except Exception as e:
                    log.error(f"Unexpected error deleting channel {channel.name}: {e}", exc_info=True)
                    raise
        
        log.info("Channel and category cleanup completed successfully")
    
    async def _cleanup_existing_roles(self) -> None:
        """Delete existing roles (except protected ones)."""
        # Protected roles that should not be deleted
        protected_role_names = {
            "@everyone",  # Everyone role cannot be deleted
            "admin", "administrator", "mod", "moderator", "staff", "owner",
            "bot", "bots", "helper", "dev", "developer", "vip"
        } if self.guild.me.guild_permissions.administrator else {"@everyone"}
        
        # Get roles to delete (excluding protected roles and higher roles than bot)
        bot_role = self.guild.me.top_role
        roles_to_delete = []
        
        for role in self.guild.roles:
            # Skip protected roles
            if role.name.lower() in protected_role_names:
                log.info(f"Skipping protected role: {role.name}")
                continue
            
            # Skip roles higher than bot's role
            if role >= bot_role:
                log.warning(f"Skipping role {role.name} - higher than bot's role")
                continue
            
            # Skip managed roles (by bots/integrations)
            if role.managed:
                log.info(f"Skipping managed role: {role.name}")
                continue
            
            roles_to_delete.append(role)
        
        # Delete roles in reverse order (from lowest to highest)
        roles_to_delete.sort(key=lambda r: r.position)
        
        for role in roles_to_delete:
            try:
                log.info(f"Deleting role: {role.name} (ID: {role.id})")
                await role.delete(reason="833s Guardian Overhaul V3 - Cleanup")
            except discord.Forbidden as e:
                log.error(f"Failed to delete role {role.name}: Missing permissions - {e}")
                raise
            except discord.HTTPException as e:
                log.error(f"Failed to delete role {role.name}: Discord API error - {e}")
                raise
            except Exception as e:
                log.error(f"Unexpected error deleting role {role.name}: {e}", exc_info=True)
                raise
        
        log.info("Role cleanup completed successfully")
    
    async def _apply_server_settings(self) -> None:
        """Apply server-wide settings."""
        await self.guild.edit(
            verification_level=discord.VerificationLevel.high,
            default_notifications=discord.NotificationLevel.only_mentions,
            explicit_content_filter=discord.ContentFilter.all_members,
            reason="833s Guardian Overhaul V3"
        )
    
    async def _create_roles(self) -> dict[str, discord.Role]:
        """Create server roles."""
        role_map = {}
        
        # Basic roles with proper colors
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
            try:
                role = discord.utils.get(self.guild.roles, name=role_name)
                if not role:
                    log.info(f"Creating role: {role_name}")
                    role = await self.guild.create_role(
                        name=role_name,
                        color=color,
                        hoist=hoist,
                        mentionable=mentionable,
                        reason="833s Guardian Overhaul V3"
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
        
        log.info(f"Role creation completed. Total roles: {len(role_map)}")
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
            try:
                category = discord.utils.get(self.guild.categories, name=cat_config["name"])
                if not category:
                    log.info(f"Creating category: {cat_config['name']}")
                    category = await self.guild.create_category(
                        name=cat_config["name"],
                        reason="833s Guardian Overhaul V3"
                    )
                    log.info(f"Successfully created category: {cat_config['name']} (ID: {category.id})")
                else:
                    log.info(f"Category already exists: {cat_config['name']} (ID: {category.id})")
                
                for channel_config in cat_config["channels"]:
                    try:
                        if channel_config["type"] == "text":
                            log.info(f"Creating text channel: {channel_config['name']} in category {cat_config['name']}")
                            channel = await category.create_text_channel(
                                name=channel_config["name"],
                                reason="833s Guardian Overhaul V3"
                            )
                            log.info(f"Successfully created text channel: {channel_config['name']} (ID: {channel.id})")
                        else:
                            log.info(f"Creating voice channel: {channel_config['name']} in category {cat_config['name']}")
                            channel = await category.create_voice_channel(
                                name=channel_config["name"],
                                reason="833s Guardian Overhaul V3"
                            )
                            log.info(f"Successfully created voice channel: {channel_config['name']} (ID: {channel.id})")
                            
                    except discord.Forbidden as e:
                        log.error(f"Failed to create channel {channel_config['name']}: Missing permissions - {e}")
                        raise
                    except discord.HTTPException as e:
                        log.error(f"Failed to create channel {channel_config['name']}: Discord API error - {e}")
                        raise
                    except Exception as e:
                        log.error(f"Unexpected error creating channel {channel_config['name']}: {e}", exc_info=True)
                        raise
                        
            except discord.Forbidden as e:
                log.error(f"Failed to create category {cat_config['name']}: Missing permissions - {e}")
                raise
            except discord.HTTPException as e:
                log.error(f"Failed to create category {cat_config['name']}: Discord API error - {e}")
                raise
            except Exception as e:
                log.error(f"Unexpected error creating category {cat_config['name']}: {e}", exc_info=True)
                raise
        
        log.info("Category and channel creation completed successfully")
    
    async def _setup_leveling_system(self, role_map: dict[str, discord.Role]) -> None:
        """Configure leveling system with role rewards."""
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
        level_rewards = {
            1: role_map.get("Bronze"),
            5: role_map.get("Silver"),
            10: role_map.get("Gold"),
            25: role_map.get("Platinum"),
            50: role_map.get("Diamond"),
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
        """Configure bot modules."""
        try:
            # Configure welcome channel
            welcome_channel = discord.utils.get(self.guild.text_channels, name="rules")
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
        """Final cleanup and optimizations."""
        log.info("Starting overhaul finalization")
        
        # Set server icon if available
        if "server_icon" in self.config:
            try:
                log.info("Setting server icon")
                await self.guild.edit(icon=self.config["server_icon"])
                log.info("Server icon set successfully")
            except discord.Forbidden as e:
                log.error(f"Failed to set server icon: Missing permissions - {e}")
            except discord.HTTPException as e:
                log.error(f"Failed to set server icon: Discord API error - {e}")
            except Exception as e:
                log.error(f"Unexpected error setting server icon: {e}", exc_info=True)
        
        # Additional cleanup operations can be added here
        log.info("Overhaul finalization completed")
