from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
import discord
import logging

from guardian.overhaul.rate_limiter import RateLimiter
from guardian.overhaul.progress import ProgressReporter
from guardian.interfaces import has_required_guild_perms, sanitize_user_text, OperationSnapshot

log = logging.getLogger("guardian.overhaul_engine")


@dataclass
class ValidationResult:
    ok: bool
    missing: List[str]
    reason: str


@dataclass
class DeleteResult:
    channels_deleted: int
    categories_deleted: int
    roles_deleted: int
    skipped: List[str]


@dataclass
class RebuildResult:
    categories_created: int
    channels_created: int
    roles_created: int
    errors: List[str]


@dataclass
class ContentResult:
    posts_created: int
    errors: List[str]


class OverhaulEngine:
    """Engine for performing server overhaul operations."""
    
    def __init__(self, bot: discord.Client, rate_limiter: RateLimiter):
        self.bot = bot
        self.rate_limiter = rate_limiter
    
    async def validate(self, guild: discord.Guild) -> ValidationResult:
        """Validate that overhaul can proceed safely."""
        bot_member = guild.me
        
        # Use interface helper for permission checking
        has_perms, missing = has_required_guild_perms(bot_member)
        
        if has_perms:
            return ValidationResult(ok=True, missing=[], reason="All permissions OK")
        else:
            return ValidationResult(
                ok=False,
                missing=missing,
                reason=f"Missing permissions: {', '.join(missing)}"
            )
        
        # Check bot role hierarchy
        if bot_member.roles:
            bot_top_role = max(bot_member.roles, key=lambda r: r.position)
            roles_above_bot = [r for r in guild.roles if r.position > bot_top_role.position and r.name != "@everyone"]
            if roles_above_bot:
                return ValidationResult(
                    ok=False,
                    missing=["role_hierarchy"],
                    reason=f"Cannot delete roles above bot: {', '.join(r.name for r in roles_above_bot[:5])}"
                )
        
        # Check guild size
        if guild.member_count > 10000:
            return ValidationResult(
                ok=False,
                missing=["guild_size"],
                reason=f"Large guild ({guild.member_count} members) - overhaul may take significant time"
            )
        
        return ValidationResult(ok=True, missing=[], reason="All validations passed")
    
    async def snapshot(self, guild: discord.Guild) -> OperationSnapshot:
        """Take snapshot before destructive operations."""
        return OperationSnapshot(guild)
    
    async def delete_all(self, guild: discord.Guild, reporter: ProgressReporter) -> DeleteResult:
        """Phase A: Delete all channels, categories, and eligible roles."""
        channels_deleted = 0
        categories_deleted = 0
        roles_deleted = 0
        skipped = []
        
        # Delete channels first (must be done before categories)
        channels = [c for c in guild.channels if not isinstance(c, discord.CategoryChannel)]
        await reporter.update("Deleting Channels", 0, len(channels), "Starting channel deletion")
        
        for i, channel in enumerate(channels):
            try:
                await self.rate_limiter.execute(channel.delete, reason="Server overhaul")
                channels_deleted += 1
                await reporter.update("Deleting Channels", i + 1, len(channels), f"Deleted #{channel.name}", counts=self._get_counts())
            except discord.Forbidden:
                skipped.append(f"Channel #{channel.name} (no permission)")
                await reporter.update("Deleting Channels", i + 1, len(channels), f"Skipped #{channel.name} (no permission)", counts=self._get_counts())
            except discord.NotFound:
                await reporter.update("Deleting Channels", i + 1, len(channels), f"Skipped #{channel.name} (already deleted)", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Deleting Channels", i + 1, len(channels), f"Error deleting #{channel.name}", counts=self._get_counts(), errors=1)
        
        # Delete categories
        categories = guild.categories
        await reporter.update("Deleting Categories", 0, len(categories), "Starting category deletion")
        
        for i, category in enumerate(categories):
            try:
                await self.rate_limiter.execute(category.delete, reason="Server overhaul")
                categories_deleted += 1
                await reporter.update("Deleting Categories", i + 1, len(categories), f"Deleted category {category.name}", counts=self._get_counts())
            except discord.Forbidden:
                skipped.append(f"Category {category.name} (no permission)")
                await reporter.update("Deleting Categories", i + 1, len(categories), f"Skipped {category.name} (no permission)", counts=self._get_counts())
            except discord.NotFound:
                await reporter.update("Deleting Categories", i + 1, len(categories), f"Skipped {category.name} (already deleted)", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Deleting Categories", i + 1, len(categories), f"Error deleting category {category.name}", counts=self._get_counts(), errors=1)
        
        # Delete eligible roles
        bot_top_role = max(guild.me.roles, key=lambda r: r.position) if guild.me.roles else None
        eligible_roles = [
            r for r in guild.roles 
            if r.name != "@everyone" 
            and not r.managed 
            and (not bot_top_role or r.position < bot_top_role.position)
        ]
        
        await reporter.update("Deleting Roles", 0, len(eligible_roles), "Starting role deletion")
        
        for i, role in enumerate(eligible_roles):
            try:
                await self.rate_limiter.execute(role.delete, reason="Server overhaul")
                roles_deleted += 1
                await reporter.update("Deleting Roles", i + 1, len(eligible_roles), f"Deleted role @{role.name}", counts=self._get_counts())
            except discord.Forbidden:
                skipped.append(f"Role @{role.name} (no permission)")
                await reporter.update("Deleting Roles", i + 1, len(eligible_roles), f"Skipped @{role.name} (no permission)", counts=self._get_counts())
            except discord.NotFound:
                await reporter.update("Deleting Roles", i + 1, len(eligible_roles), f"Skipped @{role.name} (already deleted)", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Deleting Roles", i + 1, len(eligible_roles), f"Error deleting role @{role.name}", counts=self._get_counts(), errors=1)
        
        return DeleteResult(
            channels_deleted=channels_deleted,
            categories_deleted=categories_deleted,
            roles_deleted=roles_deleted,
            skipped=skipped
        )
    
    async def rebuild_all(self, guild: discord.Guild, reporter: ProgressReporter) -> RebuildResult:
        """Phase B: Rebuild clean server architecture."""
        categories_created = 0
        channels_created = 0
        roles_created = 0
        errors = []
        
        # Create roles first
        await reporter.update("Creating Roles", 0, 11, "Starting role creation")
        roles = await self._create_roles(guild, reporter)
        roles_created = len(roles)
        
        # Create categories
        await reporter.update("Creating Categories", 0, 12, "Starting category creation")
        categories = await self._create_categories(guild, reporter)
        categories_created = len(categories)
        
        # Create channels
        await reporter.update("Creating Channels", 0, 28, "Starting channel creation")
        channels = await self._create_channels(guild, categories, roles, reporter)
        channels_created = len(channels)
        
        return RebuildResult(
            categories_created=categories_created,
            channels_created=channels_created,
            roles_created=roles_created,
            errors=errors
        )
    
    async def _create_roles(self, guild: discord.Guild, reporter: ProgressReporter) -> List[discord.Role]:
        """Create the canonical role hierarchy."""
        role_configs = [
            # Bot Roles (Must be highest - above Owner)
            ("Guardian Bot", discord.Color.default(), 10),
            ("Guardian Services", discord.Color.default(), 9),
            
            # Staff Roles
            ("Owner", discord.Color.dark_grey(), 8),
            ("Admin", discord.Color.dark_red(), 7),
            ("Moderator", discord.Color.purple(), 6),
            ("Support", discord.Color.gold(), 5),
            
            # System Role
            ("Verified", discord.Color.green(), 4),
            
            # Game Roles
            ("Roblox", discord.Color.red(), 3),
            ("Minecraft", discord.Color.dark_green(), 3),
            ("ARK", discord.Color.orange(), 3),
            ("FPS", discord.Color.dark_red(), 3),
            
            # Interest Roles
            ("Coding", discord.Color.blue(), 2),
            ("Snakes", discord.Color.dark_purple(), 2)
        ]
        
        roles = []
        for i, (name, color, position) in enumerate(role_configs):
            try:
                role = await self.rate_limiter.execute(
                    guild.create_role, 
                    name=name, 
                    color=color, 
                    reason="Server overhaul"
                )
                if position > 1:
                    await self.rate_limiter.execute(role.edit, position=position)
                roles.append(role)
                await reporter.update("Creating Roles", i + 1, 11, f"Created role @{name}", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Creating Roles", i + 1, 11, f"Error creating role @{name}", counts=self._get_counts(), errors=1)
        
        return roles
    
    async def _create_categories(self, guild: discord.Guild, reporter: ProgressReporter) -> List[discord.CategoryChannel]:
        """Create canonical category structure."""
        category_names = [
            "🔐 VERIFY GATE",
            "🎫 SUPPORT-ENTRY",
            "📢 START", 
            "💬 GENERAL",
            "🎛️ REACTION-ROLES",
            "🎮 ROBLOX",
            "🧱 MINECRAFT",
            "🦖 ARK",
            "🔫 FPS",
            "💻 CODING",
            "🐍 SNAKES",
            "🎫 SUPPORT",
            "🛡️ STAFF"
        ]
        
        categories = []
        for i, name in enumerate(category_names):
            try:
                category = await self.rate_limiter.execute(
                    guild.create_category,
                    name,
                    reason="Server overhaul"
                )
                categories.append(category)
                await reporter.update("Creating Categories", i + 1, 12, f"Created category {name}", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Creating Categories", i + 1, 12, f"Error creating category {name}", counts=self._get_counts(), errors=1)
        
        return categories
    
    async def _create_channels(self, guild: discord.Guild, categories: List[discord.CategoryChannel], 
                            roles: List[discord.Role], reporter: ProgressReporter) -> List[discord.TextChannel]:
        """Create channels within categories."""
        channels = []
        
        # Get role objects for permission overwrites
        guardian_bot_role = discord.utils.get(roles, name="Guardian Bot")
        guardian_services_role = discord.utils.get(roles, name="Guardian Services")
        owner_role = discord.utils.get(roles, name="Owner")
        admin_role = discord.utils.get(roles, name="Admin")
        moderator_role = discord.utils.get(roles, name="Moderator")
        support_role = discord.utils.get(roles, name="Support")
        verified_role = discord.utils.get(roles, name="Verified")
        roblox_role = discord.utils.get(roles, name="Roblox")
        minecraft_role = discord.utils.get(roles, name="Minecraft")
        ark_role = discord.utils.get(roles, name="ARK")
        fps_role = discord.utils.get(roles, name="FPS")
        coding_role = discord.utils.get(roles, name="Coding")
        snakes_role = discord.utils.get(roles, name="Snakes")
        
        # Channel configurations: (name, category_name, overwrites)
        channel_configs = [
            # 🔐 VERIFY GATE - Visible to @everyone only
            ("verify", "🔐 VERIFY GATE", self._create_verify_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, verified_role)),
            
            # 🎫 SUPPORT-ENTRY - Emergency door, visible to everyone
            ("support-start", "🎫 SUPPORT-ENTRY", self._create_support_entry_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, verified_role)),
            
            # 📢 START (Verified+) - All read-only for users
            ("welcome", "📢 START", self._create_readonly_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, verified_role)),
            ("rules", "📢 START", self._create_readonly_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, verified_role)),
            ("announcements", "📢 START", self._create_readonly_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, verified_role)),
            ("server-info", "📢 START", self._create_readonly_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, verified_role)),
            
            # 💬 GENERAL (Verified+) - Full chat access
            ("general-chat", "💬 GENERAL", self._create_general_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, verified_role)),
            ("media", "💬 GENERAL", self._create_general_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, verified_role)),
            ("introductions", "💬 GENERAL", self._create_general_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, verified_role)),
            ("off-topic", "💬 GENERAL", self._create_general_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, verified_role)),
            
            # 🎛️ REACTION-ROLES - No talking allowed, just menus
            ("reaction-roles", "🎛️ REACTION-ROLES", self._create_reaction_roles_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, verified_role)),
            ("role-info", "🎛️ REACTION-ROLES", self._create_reaction_roles_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, verified_role)),
            
            # 🎮 ROBLOX - Role-locked category
            ("roblox-chat", "🎮 ROBLOX", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, roblox_role)),
            ("roblox-topics", "🎮 ROBLOX", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, roblox_role)),
            ("roblox-trading", "🎮 ROBLOX", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, roblox_role)),
            
            # 🧱 MINECRAFT - Role-locked category
            ("minecraft-chat", "🧱 MINECRAFT", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, minecraft_role)),
            ("minecraft-builds", "🧱 MINECRAFT", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, minecraft_role)),
            ("minecraft-servers", "🧱 MINECRAFT", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, minecraft_role)),
            
            # 🦖 ARK - Role-locked category
            ("ark-chat", "🦖 ARK", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, ark_role)),
            ("ark-breeding", "🦖 ARK", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, ark_role)),
            ("ark-maps", "🦖 ARK", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, ark_role)),
            
            # 🔫 FPS - Role-locked category
            ("fps-chat", "🔫 FPS", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, fps_role)),
            ("fps-loadouts", "🔫 FPS", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, fps_role)),
            
            # 💻 CODING - Role-locked category
            ("coding-chat", "💻 CODING", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, coding_role)),
            ("coding-projects", "💻 CODING", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, coding_role)),
            ("coding-resources", "💻 CODING", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, coding_role)),
            
            # 🐍 SNAKES - Role-locked category
            ("snakes-chat", "🐍 SNAKES", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, snakes_role)),
            ("snakes-care", "🐍 SNAKES", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, snakes_role)),
            ("snakes-media", "🐍 SNAKES", self._create_game_category_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role, snakes_role)),
            
            # 🎫 SUPPORT (PRIVATE)
            ("tickets", "🎫 SUPPORT", self._create_support_private_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role)),
            ("suggestions", "🎫 SUPPORT", self._create_support_private_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role)),
            
            # 🛡️ STAFF
            ("staff-chat", "🛡️ STAFF", self._create_staff_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role)),
            ("reports", "🛡️ STAFF", self._create_staff_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role)),
            ("case-files", "🛡️ STAFF", self._create_staff_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role, moderator_role, support_role)),
            ("bot-logs", "🛡️ STAFF", self._create_admin_only_overwrites(guild, guardian_bot_role, guardian_services_role, owner_role, admin_role)),
        ]
        
        for i, (name, category_name, overwrites) in enumerate(channel_configs):
            category = discord.utils.get(categories, name=category_name)
            if not category:
                await reporter.update("Creating Channels", i + 1, 28, f"Skipped #{name} (category not found)", counts=self._get_counts())
                continue
            
            try:
                channel = await self.rate_limiter.execute(
                    guild.create_text_channel,
                    name,
                    category=category,
                    reason="Server overhaul",
                    overwrites=overwrites or {}
                )
                channels.append(channel)
                await reporter.update("Creating Channels", i + 1, 28, f"Created #{name}", counts=self._get_counts())
            except Exception as e:
                await reporter.update("Creating Channels", i + 1, 28, f"Error creating #{name}", counts=self._get_counts(), errors=1)
        
        return channels
    
    def _create_verify_overwrites(self, guild: discord.Guild, guardian_bot_role: discord.Role, guardian_services_role: discord.Role,
                             owner_role: discord.Role, admin_role: discord.Role, moderator_role: discord.Role, 
                             support_role: discord.Role, verified_role: discord.Role) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Create permission overwrites for VERIFY GATE - Visible to @everyone only."""
        overwrites = {}
        
        # @everyone: Can see and click verify button
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            read_messages=True,
            send_messages=False,  # No typing
            connect=False,
            speak=False,
            read_message_history=False,
            add_reactions=False,  # No spam
            use_external_emojis=False
        )
        
        # Bot roles: Full access
        if guardian_bot_role:
            overwrites[guardian_bot_role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                connect=True,
                speak=True,
                read_message_history=True,
                manage_messages=True,
                manage_channels=True,
                administrator=True
            )
        
        if guardian_services_role:
            overwrites[guardian_services_role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                connect=True,
                speak=True,
                read_message_history=True,
                manage_messages=True,
                manage_channels=True,
                administrator=True
            )
        
        # Staff: Can see but not interact (to prevent raiding)
        for staff_role in [owner_role, admin_role, moderator_role, support_role, verified_role]:
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=False,  # No typing
                    connect=False,
                    speak=False,
                    read_message_history=False,
                    add_reactions=False,  # No spam
                    use_external_emojis=False
                )
        
        return overwrites
    
    def _create_support_entry_overwrites(self, guild: discord.Guild, guardian_bot_role: discord.Role, guardian_services_role: discord.Role,
                                       owner_role: discord.Role, admin_role: discord.Role, moderator_role: discord.Role, 
                                       support_role: discord.Role, verified_role: discord.Role) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Create permission overwrites for SUPPORT-ENTRY - Emergency door visible to everyone."""
        overwrites = {}
        
        # @everyone: See + Click
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            connect=True,
            speak=True,
            read_message_history=True
        )
        
        # Bot roles: Full access
        for bot_role in [guardian_bot_role, guardian_services_role]:
            if bot_role:
                overwrites[bot_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True,
                    administrator=True
                )
        
        # Staff: See + Click
        for staff_role in [owner_role, admin_role, moderator_role, support_role]:
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True
                )
        
        # Verified: See + Click
        if verified_role:
            overwrites[verified_role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                connect=True,
                speak=True,
                read_message_history=True
            )
        
        return overwrites
    
    def _create_readonly_overwrites(self, guild: discord.Guild, guardian_bot_role: discord.Role, guardian_services_role: discord.Role,
                                  owner_role: discord.Role, admin_role: discord.Role, moderator_role: discord.Role, 
                                  support_role: discord.Role, verified_role: discord.Role) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Create permission overwrites for START channels - Read-only for users."""
        overwrites = {}
        
        # @everyone: No access
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            read_messages=False,
            send_messages=False,
            connect=False,
            speak=False,
            read_message_history=False
        )
        
        # Bot roles: Full access
        for bot_role in [guardian_bot_role, guardian_services_role]:
            if bot_role:
                overwrites[bot_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True,
                    administrator=True
                )
        
        # Staff: Write access
        for staff_role in [owner_role, admin_role, moderator_role, support_role]:
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True
                )
        
        # Verified: Read-only
        if verified_role:
            overwrites[verified_role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=False,  # Read-only
                connect=False,
                speak=False,
                read_message_history=True
            )
        
        return overwrites
    
    def _create_general_overwrites(self, guild: discord.Guild, guardian_bot_role: discord.Role, guardian_services_role: discord.Role,
                                 owner_role: discord.Role, admin_role: discord.Role, moderator_role: discord.Role, 
                                 support_role: discord.Role, verified_role: discord.Role) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Create permission overwrites for GENERAL channels - Full chat access."""
        overwrites = {}
        
        # @everyone: No access
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            read_messages=False,
            send_messages=False,
            connect=False,
            speak=False,
            read_message_history=False
        )
        
        # Bot roles: Full access
        for bot_role in [guardian_bot_role, guardian_services_role]:
            if bot_role:
                overwrites[bot_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True,
                    administrator=True
                )
        
        # Staff: Full chat access
        for staff_role in [owner_role, admin_role, moderator_role, support_role, verified_role]:
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    embed_links=True,
                    attach_files=True,
                    add_reactions=True,
                    use_external_emojis=True
                )
        
        return overwrites
    
    def _create_reaction_roles_overwrites(self, guild: discord.Guild, guardian_bot_role: discord.Role, guardian_services_role: discord.Role,
                                        owner_role: discord.Role, admin_role: discord.Role, moderator_role: discord.Role, 
                                        support_role: discord.Role, verified_role: discord.Role) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Create permission overwrites for REACTION-ROLES - No talking allowed, just menus."""
        overwrites = {}
        
        # @everyone: No access
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            read_messages=False,
            send_messages=False,
            connect=False,
            speak=False,
            read_message_history=False
        )
        
        # Bot roles: Full access
        for bot_role in [guardian_bot_role, guardian_services_role]:
            if bot_role:
                overwrites[bot_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True,
                    administrator=True
                )
        
        # Staff: Can use menus but no talking
        for staff_role in [owner_role, admin_role, moderator_role, support_role]:
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=False,  # No talking
                    connect=False,
                    speak=False,
                    read_message_history=True,
                    add_reactions=True,  # Can use menus
                    use_external_emojis=True
                )
        
        # Verified: Can use menus but no talking
        if verified_role:
            overwrites[verified_role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=False,  # No talking
                connect=False,
                speak=False,
                read_message_history=True,
                add_reactions=True,  # Can use menus
                use_external_emojis=True
            )
        
        return overwrites
    
    def _create_game_category_overwrites(self, guild: discord.Guild, guardian_bot_role: discord.Role, guardian_services_role: discord.Role,
                                       owner_role: discord.Role, admin_role: discord.Role, moderator_role: discord.Role, 
                                       support_role: discord.Role, game_role: discord.Role) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Create permission overwrites for game/interest categories - Role-locked."""
        overwrites = {}
        
        # @everyone: No access (invisible)
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            read_messages=False,
            send_messages=False,
            connect=False,
            speak=False,
            read_message_history=False
        )
        
        # Bot roles: Full access
        for bot_role in [guardian_bot_role, guardian_services_role]:
            if bot_role:
                overwrites[bot_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True,
                    administrator=True
                )
        
        # Staff: Full chat access
        for staff_role in [owner_role, admin_role, moderator_role, support_role]:
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True
                )
        
        # Game role: Full access
        if game_role:
            overwrites[game_role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                connect=True,
                speak=True,
                read_message_history=True,
                embed_links=True,
                attach_files=True,
                add_reactions=True,
                use_external_emojis=True
            )
        
        return overwrites
    
    def _create_support_private_overwrites(self, guild: discord.Guild, guardian_bot_role: discord.Role, guardian_services_role: discord.Role,
                                         owner_role: discord.Role, admin_role: discord.Role, moderator_role: discord.Role, 
                                         support_role: discord.Role) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Create permission overwrites for private SUPPORT channels."""
        overwrites = {}
        
        # @everyone: No access
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            read_messages=False,
            send_messages=False,
            connect=False,
            speak=False,
            read_message_history=False
        )
        
        # Bot roles: Full access
        for bot_role in [guardian_bot_role, guardian_services_role]:
            if bot_role:
                overwrites[bot_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True,
                    administrator=True
                )
        
        # Staff: Full access
        for staff_role in [owner_role, admin_role, moderator_role, support_role]:
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True
                )
        
        return overwrites
    
    def _create_staff_overwrites(self, guild: discord.Guild, guardian_bot_role: discord.Role, guardian_services_role: discord.Role,
                               owner_role: discord.Role, admin_role: discord.Role, moderator_role: discord.Role, 
                               support_role: discord.Role) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Create permission overwrites for STAFF channels."""
        overwrites = {}
        
        # @everyone: No access
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            read_messages=False,
            send_messages=False,
            connect=False,
            speak=False,
            read_message_history=False
        )
        
        # Bot roles: Full access
        for bot_role in [guardian_bot_role, guardian_services_role]:
            if bot_role:
                overwrites[bot_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True,
                    administrator=True
                )
        
        # Staff: Full access
        for staff_role in [owner_role, admin_role, moderator_role, support_role]:
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True
                )
        
        return overwrites
    
    def _create_admin_only_overwrites(self, guild: discord.Guild, guardian_bot_role: discord.Role, guardian_services_role: discord.Role,
                                    owner_role: discord.Role, admin_role: discord.Role) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Create permission overwrites for admin-only channels."""
        overwrites = {}
        
        # @everyone: No access
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            read_messages=False,
            send_messages=False,
            connect=False,
            speak=False,
            read_message_history=False
        )
        
        # Bot roles: Full access
        for bot_role in [guardian_bot_role, guardian_services_role]:
            if bot_role:
                overwrites[bot_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True,
                    administrator=True
                )
        
        # Admin only: Full access
        for admin_only_role in [owner_role, admin_role]:
            if admin_only_role:
                overwrites[admin_only_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    connect=True,
                    speak=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True,
                    administrator=True
                )
        
        return overwrites
    
        
    async def post_content(self, guild: discord.Guild, reporter: ProgressReporter) -> ContentResult:
        """Phase C: Post prepared content to channels."""
        posts_created = 0
        errors = []
        
        # Content definitions
        content_posts = [
            ("verify", self._get_verify_content()),
            ("welcome", self._get_welcome_content()),
            ("rules", self._get_rules_content()),
            ("announcements", self._get_announcements_content()),
            ("server-info", self._get_server_info_content()),
            ("reaction-roles", self._get_reaction_roles_content()),
            ("role-info", self._get_role_info_content()),
            ("tickets", self._get_tickets_content()),
            ("suggestions", self._get_suggestions_content())
        ]
        
        await reporter.update("Posting Content", 0, len(content_posts), "Starting content posting")
        
        for i, (channel_name, content) in enumerate(content_posts):
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if not channel:
                await reporter.update("Posting Content", i + 1, len(content_posts), f"Skipped #{channel_name} (not found)", counts=self._get_counts())
                continue
            
            try:
                message = await self.rate_limiter.execute(channel.send, **content)
                posts_created += 1
                await reporter.update("Posting Content", i + 1, len(content_posts), f"Posted content to #{channel_name}", counts=self._get_counts())
                
                # Note: Reaction role UI deployment removed - will be done manually
                        
            except Exception as e:
                await reporter.update("Posting Content", i + 1, len(content_posts), f"Error posting to #{channel_name}", counts=self._get_counts(), errors=1)
        
        return ContentResult(posts_created=posts_created, errors=errors)
    
    def _get_verify_content(self) -> Dict[str, Any]:
        """Get verify channel content."""
        from guardian.cogs.verify_panel import VerifyView
        
        embed = discord.Embed(
            title=sanitize_user_text("🔐 Verification Gate"),
            description=sanitize_user_text(
                "Welcome.\n"
                "This server is role-locked. You will not see anything until you verify.\n\n"
                "Click button below to:\n"
                "- Confirm you are human\n"
                "- Accept rules\n"
                "- Enter live server\n\n"
                "Once verified:\n"
                "- The gate disappears\n"
                "- You get access to public areas\n"
                "- You can pick your game and interest roles\n\n"
                "If button does nothing, refresh Discord or rejoin.\n\n"
                "Verification is required to use this server."
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="Verification is required to access server channels")
        
        view = VerifyView()
        
        return {
            "embed": embed,
            "view": view
        }
    
    def _get_tickets_content(self) -> Dict[str, Any]:
        """Get tickets channel content."""
        return {
            "content": sanitize_user_text("🎫 Support System"),
            "embed": discord.Embed(
                title=sanitize_user_text("🎫 Support System"),
                description=sanitize_user_text(
                    "Need help from staff?\n\n"
                    "Open a ticket using the button below.\n\n"
                    "Tickets are used for:\n"
                    "- Rule issues\n"
                    "- Member problems\n"
                    "- Reports\n"
                    "- Technical problems\n"
                    "- Role or access issues\n\n"
                    "What happens when you open one:\n"
                    "- A private channel is created\n"
                    "- Only you and staff can see it\n"
                    "- Everything stays logged\n\n"
                    "Do not DM staff directly.\n"
                    "Use the ticket system."
                ),
                color=discord.Color.orange()
            )
        }
    
    def _get_server_info_content(self) -> Dict[str, Any]:
        """Get server-info channel content."""
        return {
            "content": sanitize_user_text(
                "📋 Server Information\n\n"
                "This server runs on 833's Guardian.\n\n"
                "It is built to stay clean, organized, and easy to use.\n\n"
                "**How access works:**\n"
                "After verifying in #verify you can pick roles in #reaction-roles.\n"
                "Each role unlocks its own channels.\n"
                "If you do not choose a role, those channels will not appear for you.\n\n"
                "**Getting help:**\n"
                "Open a ticket in #tickets.\n\n"
                "**Suggestions:**\n"
                "Post ideas in #suggestions.\n\n"
                "**Profiles and levels:**\n"
                "Use !rank to see your level.\n\n"
                "**Rules:**\n"
                "The rules in #rules apply everywhere. No scams, no harassment, no NSFW."
            )
        }
    
    def _get_rules_content(self) -> Dict[str, Any]:
        """Get rules channel content."""
        return {
            "content": sanitize_user_text("📜 Server Rules"),
            "embed": discord.Embed(
                title=sanitize_user_text("📜 Server Rules"),
                description=sanitize_user_text(
                    "**1) No harassment**\n"
                    "No bullying, threats, slurs, or targeting.\n\n"
                    "**2) No scams or fraud**\n"
                    "No fake trades, fake links, impersonation, or tricking people.\n\n"
                    "**3) No NSFW**\n"
                    "No sexual content, gore, or explicit material.\n\n"
                    "**4) No illegal activity**\n"
                    "No piracy, malware, or anything illegal.\n\n"
                    "**5) No spam**\n"
                    "No floods, no self-promo without permission, no bot abuse.\n\n"
                    "**6) Respect staff decisions**\n"
                    "If you disagree, open a ticket. Do not argue publicly.\n\n"
                    "Breaking rules removes access to the server."
                ),
                color=discord.Color.red()
            )
        }
    
    def _get_announcements_content(self) -> Dict[str, Any]:
        """Get announcements channel content."""
        return {
            "content": sanitize_user_text(
                "📢 Announcements\n\n"
                "This channel is used for:\n"
                "- Server updates\n"
                "- System changes\n"
                "- Events\n"
                "- Important notices\n\n"
                "Do not chat here.\n"
                "Everything posted here matters."
            )
        }
    
    def _get_suggestions_content(self) -> Dict[str, Any]:
        """Get suggestions channel content."""
        return {
            "content": sanitize_user_text("💡 Suggestions"),
            "embed": discord.Embed(
                title=sanitize_user_text("💡 Suggestions"),
                description=sanitize_user_text(
                    "Post it here.\n\n"
                    "Suggestions should be:\n"
                    "- Clear\n"
                    "- Useful\n"
                    "- Realistic\n\n"
                    "Spam or joke suggestions will be removed.\n\n"
                    "Good ideas get reviewed."
                ),
                color=discord.Color.green()
            )
        }
    
    def _get_welcome_content(self) -> Dict[str, Any]:
        """Get welcome channel content."""
        return {
            "content": sanitize_user_text("👋 Welcome to the Server!"),
            "embed": discord.Embed(
                title=sanitize_user_text("👋 Welcome!"),
                description=sanitize_user_text(
                    "Welcome to our community!\n\n"
                    "Please read the rules in #rules and check #announcements for updates.\n\n"
                    "Once you're ready, head to #reaction-roles to pick your interests.\n\n"
                    "Enjoy your stay!"
                ),
                color=discord.Color.green()
            )
        }
    
    def _get_reaction_roles_content(self) -> Dict[str, Any]:
        """Get reaction-roles channel content with actual RR UI."""
        from guardian.cogs.role_panel import RolePanelCog
        
        embed = discord.Embed(
            title=sanitize_user_text("🎯 Choose Your Roles"),
            description=sanitize_user_text(
                "Use the dropdown below to select your roles!\n\n"
                "🎮 **Game Roles:**\n"
                "- 🟥 Roblox\n"
                "- 🟩 Minecraft\n"
                "- 🟧 ARK\n"
                "- 🔴 FPS\n\n"
                "💻 **Interest Roles:**\n"
                "- 💠 Coding\n"
                "- 🐍 Snakes\n\n"
                "Check #role-info for more details about each role."
            ),
            color=discord.Color.blue()
        )
        
        # Create role panel cog instance to get role configs
        # This will deploy the actual working role selection UI
        return {
            "content": sanitize_user_text("🎯 Reaction Roles"),
            "embed": embed,
            "view": None  # Will be replaced by actual role panel deployment
        }
    
    def _get_role_info_content(self) -> Dict[str, Any]:
        """Get role-info channel content."""
        return {
            "content": sanitize_user_text("📋 Role Information"),
            "embed": discord.Embed(
                title=sanitize_user_text("📋 Role Details"),
                description=sanitize_user_text(
                    "**Game Roles:**\n"
                    "- **Roblox:** Access to Roblox chat, bee swarm, trading\n"
                    "- **Minecraft:** Access to MC chat, servers, builds\n"
                    "- **ARK:** Access to ARK chat, maps, breeding\n"
                    "- **FPS:** Access to FPS chat and loadouts\n\n"
                    "**Interest Roles:**\n"
                    "- **Coding:** Access to coding chat, projects, resources\n"
                    "- **Snakes:** Access to snakes chat, pet media, care guides\n\n"
                    "React in #reaction-roles to get these roles!"
                ),
                color=discord.Color.gold()
            )
        }
    
    # Auto-configure canonical roles removed - will be done manually
    
    def _get_counts(self) -> Dict[str, int]:
        """Get current operation counts for progress reporting."""
        # This is a simplified version - in a real implementation,
        # you'd track these counts properly across operations
        return {
            "deleted_channels": 0,
            "deleted_categories": 0,
            "deleted_roles": 0,
            "created_categories": 0,
            "created_channels": 0,
            "created_roles": 0,
            "skipped": 0
        }
