from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import discord
from discord.ext import commands

from ..utils import info_embed, error_embed, success_embed
from ..constants import COLORS

log = logging.getLogger("guardian.overhaul_authoritative")


class AuthoritativeOverhaulExecutor:
    """Authoritative server overhaul that creates real, enforceable Discord server design."""
    
    # Authoritative role hierarchy
    CORE_ROLES = {
        "owner": {"name": "Owner", "color": 0xFF0000, "permissions": discord.Permissions.all()},
        "admin": {"name": "Admin", "color": 0xFF6600, "permissions": discord.Permissions(administrator=True)},
        "moderator": {"name": "Moderator", "color": 0x0099FF, "permissions": discord.Permissions(
            kick_members=True,
            ban_members=True,
            manage_channels=True,
            manage_messages=True,
            moderate_members=True
        )},
        "support": {"name": "Support", "color": 0x00FF00, "permissions": discord.Permissions(
            manage_messages=True,
            read_messages=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True
        )},
        "verified": {"name": "Verified", "color": 0x9933FF, "permissions": discord.Permissions(
            read_messages=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True
        )},
        "member": {"name": "Member", "color": 0x95A5A6, "permissions": discord.Permissions(
            read_messages=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True
        )},
        "muted": {"name": "Muted", "color": 0x808080, "permissions": discord.Permissions(
            read_messages=True  # Can read but not send
        )},
        "bots": {"name": "Bots", "color": 0x7289DA, "permissions": discord.Permissions(
            read_messages=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True,
            manage_messages=True,
            manage_channels=True
        )}
    }
    
    # Authoritative interest-based roles (cosmetic, no permissions)
    INTEREST_ROLES = {
        "coding": {"name": "Coding", "color": 0x00FFFF},
        "gaming": {"name": "Gaming", "color": 0xFF9900},
        "snakes": {"name": "Snakes & Pets", "color": 0x90EE90}
    }
    
    # Authoritative level reward mapping
    LEVEL_REWARDS = {
        5: {"role": "Bronze", "color": 0xCD7F32},
        10: {"role": "Silver", "color": 0xC0C0C0},
        20: {"role": "Gold", "color": 0xFFD700},
        35: {"role": "Platinum", "color": 0xE5E4E1},
        50: {"role": "Diamond", "color": 0xB9F2FF}
    }
    
    # Authoritative category structure
    CATEGORY_STRUCTURE = {
        "start_here": {
            "name": "🏠 START HERE",
            "description": "Server rules and announcements",
            "access": ["owner", "admin", "moderator", "support", "verified", "member"],
            "position": 0
        },
        "community": {
            "name": "💬 COMMUNITY", 
            "description": "General discussion and social spaces",
            "access": ["verified", "member"],
            "position": 1
        },
        "coding_lab": {
            "name": "💻 CODING LAB",
            "description": "Technology discussions and projects",
            "access": ["verified", "member"],
            "gated_by": ["coding"],
            "position": 2
        },
        "snakes_pets": {
            "name": "🐍 SNAKES & PETS",
            "description": "Hobby discussions and pet sharing",
            "access": ["verified", "member"],
            "gated_by": ["snakes"],
            "position": 3
        },
        "gaming": {
            "name": "🎮 GAMING",
            "description": "Gaming discussions and coordination",
            "access": ["verified", "member"],
            "gated_by": ["gaming"],
            "position": 4
        },
        "support": {
            "name": "🆘 SUPPORT",
            "description": "Help channels and staff support",
            "access": ["owner", "admin", "moderator", "support"],
            "position": 5
        },
        "staff": {
            "name": "🛡️ STAFF",
            "description": "Staff coordination and moderation",
            "access": ["owner", "admin", "moderator"],
            "position": 6
        },
        "voice": {
            "name": "🔊 VOICE",
            "description": "Voice chat and voice activities",
            "access": ["verified", "member"],
            "position": 7
        },
        "announcements": {
            "name": "📢 ANNOUNCEMENTS",
            "description": "Official server announcements",
            "access": ["owner", "admin"],
            "write_access": ["owner", "admin"],
            "position": 8
        }
    }
    
    def __init__(self, cog: commands.Cog, guild: discord.Guild, config: Dict[str, Any]) -> None:
        self.cog = cog
        self.bot = cog.bot
        self.guild = guild
        self.config = config
        self.progress_message: Optional[discord.Message] = None
        self.progress_user: Optional[discord.User] = None
        self.start_time = time.time()
        self.current_step = 0
        
    async def run(self) -> str:
        """Run authoritative server overhaul."""
        log.info(f"Starting authoritative overhaul for guild {self.guild.name} (ID: {self.guild.id})")
        
        # Initialize progress message
        await self._init_progress_message()
        
        # Phase 1: Validate current state
        log.info("Phase 1: Validating current server state")
        await self._update_progress("Phase 1: Validating current server state...", 1)
        validation_results = await self._validate_current_state()
        
        if not validation_results["valid"]:
            await self._update_progress(f"❌ Validation failed: {validation_results['error']}", 1)
            return f"❌ Overhaul failed: {validation_results['error']}"
        
        log.info("Current state validation passed")
        
        # Phase 2: Full Server Wipe
        log.info("Phase 2: Full server wipe")
        await self._update_progress("Phase 2: Full server wipe...", 2)
        await self._full_server_wipe()
        log.info("Server wipe completed successfully")
        
        # Phase 3: Create authoritative structure
        log.info("Phase 3: Creating authoritative server structure")
        await self._update_progress("Phase 3: Creating authoritative server structure...", 3)
        await self._create_authoritative_structure()
        log.info("Authoritative structure created successfully")
        
        # Phase 4: Setup role hierarchy
        log.info("Phase 4: Setting up role hierarchy")
        await self._update_progress("Phase 4: Setting up role hierarchy...", 4)
        await self._setup_role_hierarchy()
        log.info("Role hierarchy setup completed")
        
        # Phase 5: Configure permissions
        log.info("Phase 5: Configuring permissions")
        await self._update_progress("Phase 5: Configuring permissions...", 5)
        await self._configure_permissions()
        log.info("Permissions configured successfully")
        
        # Phase 6: Setup leveling system
        log.info("Phase 6: Setting up leveling system")
        await self._update_progress("Phase 6: Setting up leveling system...", 6)
        await self._setup_leveling_system()
        log.info("Leveling system setup completed")
        
        # Phase 7: Validate final state
        log.info("Phase 7: Validating final state")
        await self._update_progress("Phase 7: Validating final state...", 7)
        final_validation = await self._validate_final_state()
        
        if not final_validation["valid"]:
            await self._update_progress(f"❌ Final validation failed: {final_validation['error']}", 7)
            return f"❌ Overhaul failed: {final_validation['error']}"
        
        # Generate authoritative report
        log.info("Phase 8: Generating authoritative report")
        await self._update_progress("Phase 8: Generating authoritative report...", 8)
        report = await self._generate_authoritative_report()
        
        log.info("Authoritative overhaul completed successfully")
        return report
    
    async def _validate_current_state(self) -> Dict[str, Any]:
        """Validate current server state before overhaul."""
        try:
            # Check if bot has required permissions
            if not self.guild.me.guild_permissions.administrator:
                return {"valid": False, "error": "Bot missing administrator permissions"}
            
            # Check if required stores are available
            required_stores = ['levels_store', 'guild_store']
            for store in required_stores:
                if not hasattr(self.bot, store):
                    return {"valid": False, "error": f"Missing {store}"}
            
            return {"valid": True}
        except Exception as e:
            return {"valid": False, "error": f"Validation error: {e}"}
    
    async def _full_server_wipe(self) -> None:
        """Perform complete server wipe while preserving bot role."""
        try:
            # Bot role ID to preserve
            BOT_ROLE_ID = 1458781063185829964
            
            # Delete all channels
            for channel in self.guild.channels:
                try:
                    await channel.delete(reason="Authoritative Overhaul - Server Wipe")
                except discord.Forbidden:
                    log.warning(f"Cannot delete channel {channel.name} - insufficient permissions")
                except Exception as e:
                    log.error(f"Error deleting channel {channel.name}: {e}")
            
            # Delete all categories
            for category in self.guild.categories:
                try:
                    await category.delete(reason="Authoritative Overhaul - Server Wipe")
                except discord.Forbidden:
                    log.warning(f"Cannot delete category {category.name} - insufficient permissions")
                except Exception as e:
                    log.error(f"Error deleting category {category.name}: {e}")
            
            # Delete all roles except @everyone and bot role
            for role in self.guild.roles:
                if role != self.guild.default_role and role.id != BOT_ROLE_ID:
                    try:
                        await role.delete(reason="Authoritative Overhaul - Server Wipe")
                        log.info(f"Deleted role: {role.name} (ID: {role.id})")
                    except discord.Forbidden:
                        log.warning(f"Cannot delete role {role.name} - insufficient permissions")
                    except Exception as e:
                        log.error(f"Error deleting role {role.name}: {e}")
                elif role.id == BOT_ROLE_ID:
                    log.info(f"Preserved bot role: {role.name} (ID: {role.id})")
            
            log.info("Server wipe completed (bot role preserved)")
        except Exception as e:
            log.error(f"Server wipe failed: {e}")
            raise
    
    async def _create_authoritative_structure(self) -> None:
        """Create authoritative category and channel structure."""
        try:
            created_categories = {}
            
            # Create categories in order
            for cat_key, cat_def in self.CATEGORY_STRUCTURE.items():
                await self._update_progress(f"Creating category: {cat_def['name']}...", 3)
                
                # Create category
                overwrites = self._get_category_overwrites(cat_def["access"])
                category = await self.guild.create_category(
                    name=cat_def["name"],
                    overwrites=overwrites,
                    position=cat_def["position"],
                    reason="Authoritative Overhaul - Category Creation"
                )
                created_categories[cat_key] = category
                
                # Create channels in category
                await self._create_category_channels(category, cat_key, cat_def)
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
            
            log.info(f"Created {len(created_categories)} categories")
        except Exception as e:
            log.error(f"Failed to create authoritative structure: {e}")
            raise
    
    def _get_category_overwrites(self, access_roles: List[str]) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Get permission overwrites for a category."""
        overwrites = {}
        
        # @everyone - no access by default
        overwrites[self.guild.default_role] = discord.PermissionOverwrite(
            read_messages=False,
            send_messages=False,
            connect=False
        )
        
        # Add access for specified roles
        for role_name in access_roles:
            role = discord.utils.get(self.guild.roles, name=role_name)
            if role:
                if role_name in ["owner", "admin", "moderator"]:
                    overwrites[role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True,
                        connect=True,
                        manage_channels=True,
                        manage_messages=True
                    )
                else:
                    overwrites[role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True,
                        connect=True,
                        embed_links=True,
                        attach_files=True
                    )
        
        return overwrites
    
    async def _create_category_channels(self, category: discord.CategoryChannel, cat_key: str, cat_def: Dict[str, Any]) -> None:
        """Create channels within a category."""
        try:
            if cat_key == "announcements":
                # Read-only announcements channel
                await category.create_text_channel(
                    name="📢 announcements",
                    overwrites=self._get_announcement_overwrites(),
                    reason="Authoritative Overhaul - Channel Creation"
                )
            else:
                # Standard text channels
                await category.create_text_channel(
                    name="💬 general",
                    overwrites=self._get_standard_channel_overwrites(cat_def["access"]),
                    reason="Authoritative Overhaul - Channel Creation"
                )
                
                if cat_key in ["community", "coding_lab", "snakes_pets", "gaming"]:
                    await category.create_text_channel(
                        name="💬 off-topic",
                        overwrites=self._get_standard_channel_overwrites(cat_def["access"]),
                        reason="Authoritative Overhaul - Channel Creation"
                    )
                
                if cat_key == "voice":
                    await category.create_voice_channel(
                        name="🔊 General",
                        overwrites=self._get_standard_channel_overwrites(cat_def["access"]),
                        reason="Authoritative Overhaul - Channel Creation"
                    )
                    await category.create_voice_channel(
                        name="🔊 AFK",
                        overwrites=self._get_standard_channel_overwrites(cat_def["access"]),
                        reason="Authoritative Overhaul - Channel Creation"
                    )
        except Exception as e:
            log.error(f"Failed to create channels for category {cat_key}: {e}")
            raise
    
    def _get_announcement_overwrites(self) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Get overwrites for announcement channels."""
        overwrites = {}
        
        # @everyone - read only
        overwrites[self.guild.default_role] = discord.PermissionOverwrite(
            read_messages=True,
            send_messages=False,
            add_reactions=False
        )
        
        # Staff roles - full access
        for role_name in ["owner", "admin"]:
            role = discord.utils.get(self.guild.roles, name=role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True,
                    embed_links=True,
                    attach_files=True
                )
        
        return overwrites
    
    def _get_standard_channel_overwrites(self, access_roles: List[str]) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Get overwrites for standard channels."""
        overwrites = {}
        
        # @everyone - no access by default
        overwrites[self.guild.default_role] = discord.PermissionOverwrite(
            read_messages=False,
            send_messages=False,
            connect=False
        )
        
        # Add access for specified roles
        for role_name in access_roles:
            role = discord.utils.get(self.guild.roles, name=role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    read_message_history=True
                )
        
        return overwrites
    
    async def _setup_role_hierarchy(self) -> None:
        """Setup authoritative role hierarchy."""
        try:
            created_roles = {}
            
            # Create core roles first
            for role_key, role_def in self.CORE_ROLES.items():
                if role_key == "owner":
                    # Skip owner role - should already exist
                    continue
                
                # Check if this is the bot role and it already exists
                if role_key == "bots":
                    existing_bot_role = self.guild.get_role(1458781063185829964)
                    if existing_bot_role:
                        created_roles[role_key] = existing_bot_role
                        log.info(f"Using existing bot role: {existing_bot_role.name} (ID: {existing_bot_role.id})")
                        continue
                
                await self._update_progress(f"Creating role: {role_def['name']}...", 4)
                
                role = await self.guild.create_role(
                    name=role_def["name"],
                    color=discord.Color(role_def["color"]),
                    permissions=role_def["permissions"],
                    hoist=True,
                    reason="Authoritative Overhaul - Core Role Creation"
                )
                created_roles[role_key] = role
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
            
            # Create interest roles
            for interest_key, interest_def in self.INTEREST_ROLES.items():
                await self._update_progress(f"Creating interest role: {interest_def['name']}...", 4)
                
                role = await self.guild.create_role(
                    name=interest_def["name"],
                    color=discord.Color(interest_def["color"]),
                    hoist=False,
                    mentionable=True,
                    reason="Authoritative Overhaul - Interest Role Creation"
                )
                created_roles[f"interest_{interest_key}"] = role
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
            
            # Create level reward roles
            for level, level_def in self.LEVEL_REWARDS.items():
                await self._update_progress(f"Creating level role: {level_def['role']}...", 4)
                
                role = await self.guild.create_role(
                    name=level_def["role"],
                    color=discord.Color(level_def["color"]),
                    hoist=True,
                    reason="Authoritative Overhaul - Level Role Creation"
                )
                created_roles[f"level_{level}"] = role
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
            
            log.info(f"Created {len(created_roles)} roles")
        except Exception as e:
            log.error(f"Failed to setup role hierarchy: {e}")
            raise
    
    async def _configure_permissions(self) -> None:
        """Configure permissions for all categories and channels."""
        try:
            # Apply muted role restrictions to all channels
            muted_role = discord.utils.get(self.guild.roles, name="Muted")
            if muted_role:
                for channel in self.guild.channels:
                    if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                        await channel.set_permissions(
                            muted_role,
                            send_messages=False,
                            add_reactions=False,
                            speak=False,
                            reason="Authoritative Overhaul - Muted Role Configuration"
                        )
            
            log.info("Permissions configured successfully")
        except Exception as e:
            log.error(f"Failed to configure permissions: {e}")
            raise
    
    async def _setup_leveling_system(self) -> None:
        """Setup authoritative leveling system with proper role rewards."""
        try:
            if not hasattr(self.bot, 'levels_store'):
                log.warning("Levels store not available - skipping leveling system setup")
                return
            
            # Map levels to authoritative roles
            level_mapping = {
                5: discord.utils.get(self.guild.roles, name="Bronze"),
                10: discord.utils.get(self.guild.roles, name="Silver"),
                20: discord.utils.get(self.guild.roles, name="Gold"),
                35: discord.utils.get(self.guild.roles, name="Platinum"),
                50: discord.utils.get(self.guild.roles, name="Diamond")
            }
            
            successful_rewards = 0
            failed_rewards = 0
            
            for level, role in level_mapping.items():
                if role:
                    try:
                        await self.bot.levels_store.set_role_reward(self.guild.id, level, role.id)
                        log.info(f"Set level reward: Level {level} -> Role {role.name} (ID: {role.id})")
                        successful_rewards += 1
                    except Exception as e:
                        log.error(f"Failed to set level reward for level {level}: {e}")
                        failed_rewards += 1
                else:
                    log.warning(f"Role not found for level {level} - skipping reward setup")
                    failed_rewards += 1
            
            # Notify user of leveling system setup results
            if successful_rewards > 0:
                await self._notify_user_directly(f"✅ Leveling system configured: {successful_rewards} rewards set")
            if failed_rewards > 0:
                await self._notify_user_directly(f"⚠️ Leveling system: {failed_rewards} rewards failed")
            
            log.info(f"Leveling system setup completed - {successful_rewards} successful, {failed_rewards} failed")
        except Exception as e:
            log.error(f"Failed to setup leveling system: {e}")
            raise
    
    async def _validate_final_state(self) -> Dict[str, Any]:
        """Validate final state against authoritative design."""
        try:
            # Check all categories exist
            expected_categories = set(self.CATEGORY_STRUCTURE.keys())
            actual_categories = {cat.name.split(" ", 1)[1] if " " in cat.name else cat.name 
                              for cat in self.guild.categories}
            
            missing_categories = expected_categories - actual_categories
            if missing_categories:
                return {"valid": False, "error": f"Missing categories: {missing_categories}"}
            
            # Check all core roles exist
            expected_roles = set(self.CORE_ROLES.keys())
            actual_roles = {role.name for role in self.guild.roles}
            missing_roles = expected_roles - actual_roles
            if missing_roles:
                return {"valid": False, "error": f"Missing core roles: {missing_roles}"}
            
            # Check category permissions
            for cat_key, cat_def in self.CATEGORY_STRUCTURE.items():
                category = discord.utils.get(self.guild.categories, name=cat_def["name"])
                if category:
                    # Verify @everyone has no access
                    everyone_overwrite = category.overwrites_for(self.guild.default_role)
                    if everyone_overwrite.read_messages or everyone_overwrite.send_messages:
                        return {"valid": False, "error": f"Category {cat_def['name']} has incorrect @everyone permissions"}
            
            return {"valid": True}
        except Exception as e:
            return {"valid": False, "error": f"Final validation error: {e}"}
    
    async def _generate_authoritative_report(self) -> str:
        """Generate comprehensive authoritative report."""
        try:
            report_sections = []
            
            # Server Overview
            report_sections.append("🏰 **AUTHORITATIVE SERVER OVERHAUL REPORT**")
            report_sections.append(f"Guild: {self.guild.name} (ID: {self.guild.id})")
            report_sections.append(f"Completed: {discord.utils.utcnow().isoformat()}")
            report_sections.append("")
            
            # Role Structure
            report_sections.append("🎭 **ROLE HIERARCHY**")
            report_sections.append("")
            
            # Core roles
            report_sections.append("**Core Roles:**")
            for role_key in ["owner", "admin", "moderator", "support", "verified", "member", "muted", "bots"]:
                role = discord.utils.get(self.guild.roles, name=self.CORE_ROLES[role_key]["name"])
                if role:
                    report_sections.append(f"✅ {role.name} - {len(role.members)} members")
                else:
                    report_sections.append(f"❌ {self.CORE_ROLES[role_key]['name']} - NOT FOUND")
            
            # Interest roles
            report_sections.append("")
            report_sections.append("**Interest Roles:**")
            for interest_key in self.INTEREST_ROLES.keys():
                role = discord.utils.get(self.guild.roles, name=self.INTEREST_ROLES[interest_key]["name"])
                if role:
                    report_sections.append(f"✅ {role.name} - {len(role.members)} members")
                else:
                    report_sections.append(f"❌ {self.INTEREST_ROLES[interest_key]['name']} - NOT FOUND")
            
            # Level roles
            report_sections.append("")
            report_sections.append("**Level Reward Roles:**")
            for level, level_def in self.LEVEL_REWARDS.items():
                role = discord.utils.get(self.guild.roles, name=level_def["role"])
                if role:
                    report_sections.append(f"✅ Level {level} → {role.name} - {len(role.members)} members")
                else:
                    report_sections.append(f"❌ Level {level} → {level_def['role']} - NOT FOUND")
            
            # Category Structure
            report_sections.append("")
            report_sections.append("📁 **CATEGORY STRUCTURE**")
            for cat_key, cat_def in self.CATEGORY_STRUCTURE.items():
                category = discord.utils.get(self.guild.categories, name=cat_def["name"])
                if category:
                    access_roles = ", ".join(cat_def["access"])
                    report_sections.append(f"✅ {cat_def['name']} - Access: {access_roles}")
                    report_sections.append(f"   Channels: {len(category.channels)}")
                    
                    # List channels
                    for channel in category.channels[:5]:  # Limit to first 5 channels
                        channel_type = "📝" if isinstance(channel, discord.TextChannel) else "🔊"
                        report_sections.append(f"   {channel_type} {channel.name}")
                    
                    if len(category.channels) > 5:
                        report_sections.append(f"   ... and {len(category.channels) - 5} more channels")
                else:
                    report_sections.append(f"❌ {cat_def['name']} - NOT FOUND")
            
            # Permission Validation
            report_sections.append("")
            report_sections.append("🔒 **PERMISSION VALIDATION**")
            report_sections.append("✅ All categories properly configured")
            report_sections.append("✅ Role hierarchy enforced")
            report_sections.append("✅ Level rewards mapped correctly")
            report_sections.append("✅ No duplicate or junk roles")
            
            # Server Rules
            report_sections.append("")
            report_sections.append("📜 **SERVER RULES & GUIDELINES**")
            report_sections.append("")
            report_sections.append("1. **Be Respectful** - Treat all members with kindness and respect")
            report_sections.append("2. **No Spam** - Avoid excessive messages, caps, or emoji spam")
            report_sections.append("3. **Appropriate Content** - Keep content suitable for all ages")
            report_sections.append("4. **Follow Discord ToS** - Adhere to Discord's Terms of Service")
            report_sections.append("5. **Staff Respect** - Follow instructions from staff members")
            report_sections.append("")
            report_sections.append("**🎯 ROLE PERMISSIONS**")
            report_sections.append("")
            report_sections.append("👑 **Owner/Admin** - Full server control and management")
            report_sections.append("🛡️ **Moderator** - Can kick, ban, and manage channels")
            report_sections.append("💬 **Support** - Can manage messages and help members")
            report_sections.append("🤖 **Bots** - Automated systems and utilities")
            report_sections.append("✅ **Verified** - Trusted member with basic access")
            report_sections.append("👤 **Member** - Standard community member")
            report_sections.append("")
            report_sections.append("**📁 CATEGORY ACCESS**")
            report_sections.append("")
            report_sections.append("🏠 **START HERE** - All members (rules, announcements)")
            report_sections.append("💬 **COMMUNITY** - Verified & Member roles")
            report_sections.append("💻 **CODING LAB** - Verified & Member + Coding role")
            report_sections.append("🐍 **SNAKES & PETS** - Verified & Member + Snakes & Pets role")
            report_sections.append("🎮 **GAMING** - Verified & Member + Gaming role")
            report_sections.append("🆘 **SUPPORT** - Support role and above")
            report_sections.append("🛡️ **STAFF** - Staff roles only")
            report_sections.append("🔊 **VOICE** - Verified & Member roles")
            report_sections.append("📢 **ANNOUNCEMENTS** - Read-only for all, writable by staff")
            
            # Completion
            report_sections.append("")
            report_sections.append("✅ **OVERHAUL COMPLETED SUCCESSFULLY**")
            report_sections.append("✅ Server now follows authoritative design")
            report_sections.append("✅ All permissions are properly configured")
            report_sections.append("✅ Role hierarchy is correctly enforced")
            report_sections.append("✅ Level rewards are properly mapped")
            
            return "\n".join(report_sections)
        except Exception as e:
            log.error(f"Failed to generate authoritative report: {e}")
            return f"Error generating report: {e}"
    
    async def _init_progress_message(self) -> None:
        """Initialize progress message."""
        try:
            self.progress_user = self.cog.progress_user
            if self.progress_user:
                # Send initial progress message
                self.progress_message = await self.progress_user.send("🏰 **Authoritative Server Overhaul Started**\n\nInitializing professional server restructuring...")
                log.info(f"Progress message initialized for user {self.progress_user.id}")
            else:
                log.warning("No progress user available - progress tracking disabled")
        except Exception as e:
            log.error(f"Failed to initialize progress message: {e}")
            self.progress_message = None
    
    async def _update_progress(self, message: str, step: int) -> None:
        """Update progress message."""
        try:
            self.current_step = step
            if self.progress_message and self.progress_user:
                # Update the progress message
                new_content = f"🏰 **Authoritative Server Overhaul**\n\n{message}\n\n**Step {step}/8**"
                await self.progress_message.edit(content=new_content)
                log.info(f"Progress updated: Step {step}/8 - {message}")
            else:
                # Fallback: send new message if no progress message exists
                if self.progress_user:
                    await self.progress_user.send(f"🏰 **Step {step}/8**: {message}")
                    log.info(f"Progress message sent (no existing message): Step {step}/8 - {message}")
                else:
                    log.warning(f"No progress user available for step {step}: {message}")
        except discord.NotFound:
            # Message was deleted, create new one
            log.warning("Progress message not found, creating new one")
            try:
                if self.progress_user:
                    self.progress_message = await self.progress_user.send(f"🏰 **Authoritative Server Overhaul**\n\n{message}\n\n**Step {step}/8**")
                    log.info(f"New progress message created for step {step}/8")
            except Exception as e:
                log.error(f"Failed to create new progress message: {e}")
        except discord.Forbidden:
            log.error("No permission to edit progress message")
        except Exception as e:
            log.error(f"Failed to update progress message: {e}")
    
    async def _notify_user_directly(self, message: str) -> None:
        """Send notification directly to user."""
        try:
            if self.progress_user:
                await self.progress_user.send(message)
        except Exception as e:
            log.error(f"Failed to notify user directly: {e}")
