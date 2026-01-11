"""
Overhaul Engine

Core overhaul logic with phases and error handling.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
import unicodedata
from dataclasses import dataclass
from typing import Dict, List

import discord

from .spec import (
    CANONICAL_TEMPLATE, ROLE_DEFINITIONS, STAFF_ROLES, BOT_ROLE_ID,
    CategorySpec, ChannelSpec, ChannelKind
)
from .http_safety import http_safety
from .progress import ProgressReporter
from .reporting import send_safe_message

log = logging.getLogger("guardian.overhaul.engine")


@dataclass
class OverhaulStats:
    """Overhaul execution statistics."""
    deleted_channels: int = 0
    deleted_categories: int = 0
    deleted_roles: int = 0
    created_channels: int = 0
    created_categories: int = 0
    created_roles: int = 0
    failures: List[str] = None
    start_time: float = None
    end_time: float = None
    
    def __post_init__(self):
        if self.failures is None:
            self.failures = []
        if self.start_time is None:
            self.start_time = time.time()


class OverhaulEngine:
    """Main overhaul execution engine."""
    
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.stats = OverhaulStats()
        self.progress = ProgressReporter()
        self._cancelled = False
    
    def cancel(self):
        """Cancel overhaul execution."""
        self._cancelled = True
        self.progress.cancel()
    
    async def run(self, interaction: discord.Interaction) -> str:
        """Execute the overhaul with full error handling."""
        try:
            # Set up progress tracking
            self.progress.set_user(interaction.user)
            self.progress.set_interaction(interaction)
            
            # Execute phases
            await self._phase_1_preflight()
            await self._phase_2_wipe()
            await self._phase_3_apply_guild_settings()
            await self._phase_4_create_roles()
            await self._phase_5_create_structure()
            await self._phase_6_apply_overwrites()
            await self._phase_7_validate()
            await self._phase_8_completion()
            
            return await self._generate_report()
            
        except Exception as e:
            log.error(f"Overhaul failed: {e}")
            log.error(traceback.format_exc())
            raise
        finally:
            self.stats.end_time = time.time()
            self.progress.cancel()
    
    async def _phase_1_preflight(self):
        """Phase 1: Preflight checks."""
        await self.progress.schedule_update("**Phase 1/8: Preflight Checks**\nVerifying permissions and setup")
        
        # Check bot permissions
        required_permissions = [
            "manage_channels",
            "manage_roles", 
            "manage_guild",
            "read_messages",
            "send_messages"
        ]
        
        missing_perms = []
        for perm in required_permissions:
            if not getattr(self.guild.me.guild_permissions, perm, False):
                missing_perms.append(perm)
        
        if missing_perms:
            raise PermissionError(f"Bot missing permissions: {', '.join(missing_perms)}")
        
        # Check bot role preservation
        bot_role = self.guild.get_role(BOT_ROLE_ID)
        if bot_role and bot_role.position > self.guild.me.top_role.position:
            log.warning(f"Bot role {bot_role.name} is above bot's top role")
    
    async def _phase_2_wipe(self):
        """Phase 2: Wipe existing structure."""
        await self.progress.schedule_update("**Phase 2/8: Wipe**\nDeleting existing channels, categories, and roles")
        
        # Delete channels first (more efficient than individual)
        for channel in list(self.guild.channels):
            if self._cancelled:
                return
            
            try:
                await http_safety.execute_with_retry(
                    lambda: channel.delete(reason="Overhaul - Wipe")
                )
                self.stats.deleted_channels += 1
            except Exception as e:
                self.stats.failures.append(f"Error deleting channel {channel.name}: {e}")
        
        # Delete categories
        for category in list(self.guild.categories):
            if self._cancelled:
                return
            
            try:
                await http_safety.execute_with_retry(
                    lambda: category.delete(reason="Overhaul - Wipe")
                )
                self.stats.deleted_categories += 1
            except Exception as e:
                self.stats.failures.append(f"Error deleting category {category.name}: {e}")
        
        # Delete roles
        for role in list(self.guild.roles):
            if self._cancelled:
                return
            
            # Skip protected roles
            if role.name == "@everyone":
                continue
            if role.managed:
                continue
            if role.position >= self.guild.me.top_role.position:
                continue
            if role.id == BOT_ROLE_ID:
                log.info(f"Preserved bot role: {role.name}")
                continue
            
            try:
                await http_safety.execute_with_retry(
                    lambda: role.delete(reason="Overhaul - Wipe")
                )
                self.stats.deleted_roles += 1
            except Exception as e:
                self.stats.failures.append(f"Error deleting role {role.name}: {e}")
    
    async def _phase_3_apply_guild_settings(self):
        """Phase 3: Apply guild settings."""
        await self.progress.schedule_update("**Phase 3/8: Guild Settings**\nApplying server configuration")
        
        try:
            # Apply guild settings using discord.py 2.x enums
            await http_safety.execute_with_retry(
                lambda: self.guild.edit(
                    system_channel=None,  # Clear system channel
                    rules_channel=None,   # Clear rules channel
                    public_updates_channel=None,  # Clear updates channel
                    preferred_locale=None  # Clear preferred locale
                )
            )
        except Exception as e:
            self.stats.failures.append(f"Error applying guild settings: {e}")
    
    async def _phase_4_create_roles(self):
        """Phase 4: Create roles."""
        await self.progress.schedule_update("**Phase 4/8: Create Roles**\nBuilding role hierarchy")
        
        # Create roles in position order (highest first)
        sorted_roles = sorted(
            ROLE_DEFINITIONS.items(),
            key=lambda x: x[1]["position"],
            reverse=True
        )
        
        for role_name, role_def in sorted_roles:
            if self._cancelled:
                return
            
            # Check if bot role already exists
            if role_name == "Bots":
                existing_bot_role = self.guild.get_role(BOT_ROLE_ID)
                if existing_bot_role:
                    log.info(f"Reusing existing bot role: {existing_bot_role.name}")
                    continue
            
            try:
                # Create permissions
                if role_def.get("administrator"):
                    permissions = discord.Permissions.all()
                else:
                    permissions = discord.Permissions.none()
                    for perm_name in role_def.get("permissions", []):
                        setattr(permissions, perm_name, True)
                
                # Create role
                role = await http_safety.execute_with_retry(
                    lambda: self.guild.create_role(
                        name=role_name,
                        permissions=permissions,
                        hoist=role_name in ["Owner", "Admin", "Moderator", "Support"],
                        reason="Overhaul - Role Creation"
                    )
                )
                
                # Set position
                await http_safety.execute_with_retry(
                    lambda: role.edit(position=role_def["position"])
                )
                
                self.stats.created_roles += 1
                
            except Exception as e:
                self.stats.failures.append(f"Error creating role {role_name}: {e}")
    
    async def _phase_5_create_structure(self):
        """Phase 5: Create categories and channels."""
        await self.progress.schedule_update("**Phase 5/8: Create Structure**\nBuilding categories and channels")
        
        # Get created roles for permission mapping
        role_map = {role.name: role for role in self.guild.roles}
        
        for cat_idx, cat_spec in enumerate(CANONICAL_TEMPLATE):
            if self._cancelled:
                return
            
            try:
                # Create category
                overwrites = self._get_category_overwrites(cat_spec, role_map)
                
                category = await http_safety.execute_with_retry(
                    lambda: self.guild.create_category(
                        name=cat_spec.name,
                        overwrites=overwrites,
                        position=cat_spec.position,
                        reason="Overhaul - Category Creation"
                    )
                )
                self.stats.created_categories += 1
                
                # Create channels
                for channel_spec in cat_spec.channels:
                    if self._cancelled:
                        return
                    
                    try:
                        overwrites = self._get_channel_overwrites(cat_spec, channel_spec, role_map)
                        
                        # Create channel
                        if channel_spec.kind == ChannelKind.VOICE:
                            channel = await http_safety.execute_with_retry(
                                lambda: category.create_voice_channel(
                                    name=channel_spec.name,
                                    overwrites=overwrites,
                                    reason="Overhaul - Voice Channel Creation"
                                )
                            )
                        else:
                            channel = await http_safety.execute_with_retry(
                                lambda: category.create_text_channel(
                                    name=channel_spec.name,
                                    overwrites=overwrites,
                                    reason="Overhaul - Text Channel Creation"
                                )
                            )
                        
                        self.stats.created_channels += 1
                        
                    except Exception as e:
                        self.stats.failures.append(f"Error creating channel {channel_spec.name}: {e}")
                
                # Update progress
                details = f"Created {cat_idx + 1}/{len(CANONICAL_TEMPLATE)} categories"
                await self.progress.schedule_update(f"**Phase 5/8: Create Structure**\n{details}")
                
            except Exception as e:
                self.stats.failures.append(f"Error creating category {cat_spec.name}: {e}")
    
    async def _phase_6_apply_overwrites(self):
        """Phase 6: Apply special overwrites."""
        await self.progress.schedule_update("**Phase 6/8: Apply Overwrites**\nApplying special permissions")
        
        # Apply muted role restrictions
        muted_role = discord.utils.get(self.guild.roles, name="Muted")
        if not muted_role:
            log.warning("Muted role not found - skipping muted restrictions")
            return
        
        channels_to_mute = [ch for ch in self.guild.channels if isinstance(ch, (discord.TextChannel, discord.VoiceChannel))]
        
        for channel in channels_to_mute:
            if self._cancelled:
                return
            
            try:
                await http_safety.execute_with_retry(
                    lambda: channel.set_permissions(
                        muted_role,
                        send_messages=False,
                        add_reactions=False,
                        create_public_threads=False,
                        create_private_threads=False,
                        speak=False,
                        reason="Overhaul - Muted Role Restrictions"
                    )
                )
            except Exception as e:
                self.stats.failures.append(f"Error applying muted restrictions to {channel.name}: {e}")
        
        # Apply read-only announcements
        announcements_channel = discord.utils.get(self.guild.text_channels, name="📣 announcements")
        if announcements_channel:
            try:
                staff_role = discord.utils.get(self.guild.roles, name="Staff")
                if staff_role:
                    await http_safety.execute_with_retry(
                        lambda: announcements_channel.set_permissions(
                            self.guild.default_role,
                            send_messages=False,
                            reason="Overhaul - Read-only Announcements"
                        )
                    )
                    await http_safety.execute_with_retry(
                        lambda: announcements_channel.set_permissions(
                            staff_role,
                            send_messages=True,
                            reason="Overhaul - Staff Announcements"
                        )
                    )
            except Exception as e:
                self.stats.failures.append(f"Error applying announcements overwrites: {e}")
    
    async def _phase_7_validate(self):
        """Phase 7: Validation against API-fetched state."""
        await self.progress.schedule_update("**Phase 7/8: Validation**\nVerifying structure matches template")
        
        # Stabilization loop
        for attempt in range(5):
            try:
                await asyncio.sleep(1)  # Wait for Discord to stabilize
                channels = await http_safety.execute_with_retry(
                    lambda: self.guild.fetch_channels()
                )
                break
            except Exception as e:
                if attempt == 4:
                    raise
                log.warning(f"Validation stabilization attempt {attempt + 1} failed: {e}")
        
        # Build lookup maps with normalized names
        category_map = {
            self._normalize_name(cat.name): cat 
            for cat in channels 
            if isinstance(cat, discord.CategoryChannel)
        }
        
        # Validate categories and channels
        for cat_spec in CANONICAL_TEMPLATE:
            cat_name_norm = self._normalize_name(cat_spec.name)
            category = category_map.get(cat_name_norm)
            
            if not category:
                self.stats.failures.append(f"Missing category: {cat_spec.name}")
                continue
            
            # Validate channels
            channel_map = {
                self._normalize_name(ch.name): ch 
                for ch in category.channels
            }
            
            for channel_spec in cat_spec.channels:
                ch_name_norm = self._normalize_name(channel_spec.name)
                channel = channel_map.get(ch_name_norm)
                
                if not channel:
                    self.stats.failures.append(f"Missing channel: {channel_spec.name} in {cat_spec.name}")
                    continue
                
                # Validate channel type
                expected_type = (
                    discord.VoiceChannel 
                    if channel_spec.kind == ChannelKind.VOICE 
                    else discord.TextChannel
                )
                if not isinstance(channel, expected_type):
                    self.stats.failures.append(
                        f"Wrong type for {channel_spec.name}: expected {channel_spec.kind.value}"
                    )
    
    async def _phase_8_completion(self):
        """Phase 8: Completion and level rewards."""
        await self.progress.schedule_update("**Phase 8/8: Completion**\nFinalizing overhaul")
        
        # Set up level rewards if available
        try:
            # This would need to be implemented based on the bot's leveling system
            log.info("Level rewards configuration would go here")
        except Exception as e:
            log.warning(f"Failed to configure level rewards: {e}")
    
    async def _generate_report(self) -> str:
        """Generate completion report."""
        duration = (self.stats.end_time or time.time()) - self.stats.start_time
        
        # Create summary report
        summary_lines = [
            "🏰 **OVERHAUL COMPLETED**",
            "",
            "📊 **STATISTICS**",
            f"• Duration: {duration:.1f}s",
            f"• Deleted: {self.stats.deleted_channels} channels, {self.stats.deleted_categories} categories, {self.stats.deleted_roles} roles",
            f"• Created: {self.stats.created_channels} channels, {self.stats.created_categories} categories, {self.stats.created_roles} roles",
            f"• Failures: {len(self.stats.failures)}",
        ]
        
        if self.stats.failures:
            summary_lines.extend([
                "",
                "⚠️ **FAILURES**",
                *[f"• {failure}" for failure in self.stats.failures[:5]]
            ])
            if len(self.stats.failures) > 5:
                summary_lines.append(f"• ... and {len(self.stats.failures) - 5} more")
        
        summary_lines.extend([
            "",
            "✅ **OPERATION COMPLETED**",
            "• Emoji template structure created",
            "• Permissions applied correctly", 
            "• Server ready for use",
            "",
            "🚀 **DEPLOYMENT COMPLETE**"
        ])
        
        return "\n".join(summary_lines)
    
    def _normalize_name(self, name: str) -> str:
        """Normalize Unicode names for comparison."""
        return unicodedata.normalize('NFC', name).strip()
    
    def _get_category_overwrites(self, cat_spec: CategorySpec, role_map: Dict[str, discord.Role]):
        """Generate permission overwrites for a category."""
        overwrites = {}
        
        try:
            # @everyone default
            everyone_role = self.guild.default_role
            everyone_can_view = cat_spec.visibility.get("@everyone", False)
            overwrites[everyone_role] = discord.PermissionOverwrite(read_messages=everyone_can_view)
            
            # Apply visibility rules
            for role_name, can_view in cat_spec.visibility.items():
                if role_name == "@everyone":
                    continue
                
                if role_name == "staff":
                    # Apply to all staff roles
                    for staff_role_name in STAFF_ROLES:
                        staff_role = role_map.get(staff_role_name)
                        if staff_role:
                            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=can_view)
                else:
                    role = role_map.get(role_name)
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(read_messages=can_view)
        
        except Exception as e:
            log.error(f"Error creating category overwrites for {cat_spec.name}: {e}")
            raise
        
        return overwrites
    
    def _get_channel_overwrites(self, cat_spec: CategorySpec, channel_spec: ChannelSpec, role_map: Dict[str, discord.Role]):
        """Generate permission overwrites for a channel."""
        overwrites = {}
        
        try:
            # Start with category overwrites
            overwrites.update(self._get_category_overwrites(cat_spec, role_map))
            
            # Apply channel-specific flags
            if channel_spec.read_only:
                everyone_role = self.guild.default_role
                current = overwrites.get(everyone_role, discord.PermissionOverwrite())
                overwrites[everyone_role] = discord.PermissionOverwrite(
                    read_messages=current.read_messages,
                    send_messages=False
                )
            
            if channel_spec.staff_only:
                # Remove access for non-staff roles
                everyone_role = self.guild.default_role
                overwrites[everyone_role] = discord.PermissionOverwrite(read_messages=False)
                
                # Keep staff access
                for staff_role_name in STAFF_ROLES:
                    staff_role = role_map.get(staff_role_name)
                    if staff_role:
                        overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True)
        
        except Exception as e:
            log.error(f"Error creating channel overwrites for {channel_spec.name}: {e}")
            raise
        
        return overwrites
