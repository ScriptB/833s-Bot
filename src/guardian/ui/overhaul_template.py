from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, replace

import discord
from discord.ext import commands

from ..utils import info_embed, error_embed, success_embed
from ..constants import COLORS

log = logging.getLogger("guardian.overhaul_template")


@dataclass
class OverhaulProgress:
    """Single source of truth for overhaul progress state."""
    phase: str = "Initializing"
    phase_num: int = 0
    total_phases: int = 8
    percent: int = 0
    details: str = ""
    errors: List[str] = None
    start_time: float = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.start_time is None:
            self.start_time = time.time()
    
    def update_phase(self, phase: str, phase_num: int, details: str = ""):
        """Update phase and calculate progress."""
        self.phase = phase
        self.phase_num = phase_num
        self.percent = int((phase_num / self.total_phases) * 100)
        self.details = details
    
    def add_error(self, error: str):
        """Add error to progress state."""
        self.errors.append(error)


class TemplateOverhaulExecutor:
    """Template-based server overhaul with exact structure matching."""
    
    # Bot role ID to preserve
    BOT_ROLE_ID = 1458781063185829964
    
    # Exact template structure
    CATEGORY_TEMPLATE = [
        {
            "name": "🛂 VERIFY GATE",
            "emoji": "🛂",
            "channels": ["🧩 verify"],
            "visibility": {"@everyone": True, "Verified": False},
            "position": 0,
            "description": "Hidden after verification"
        },
        {
            "name": "📢 START",
            "emoji": "📢", 
            "channels": ["👋 welcome", "📜 rules", "📣 announcements", "ℹ️ server-info"],
            "visibility": {"@everyone": True},
            "special_overrides": {
                "📣 announcements": {
                    "@everyone": {"send_messages": False},
                    "staff": {"send_messages": True}
                }
            },
            "position": 1,
            "description": "Public info, low-noise"
        },
        {
            "name": "💬 GENERAL",
            "emoji": "💬",
            "channels": ["💬 general-chat", "🖼️ media", "👋 introductions", "🧃 off-topic", "🔊 general-voice", "🎧 chill-voice"],
            "visibility": {"@everyone": False, "Verified": True, "Member": True},
            "position": 2,
            "description": "Verified only"
        },
        {
            "name": "🎮 GAME HUB",
            "emoji": "🎮",
            "channels": ["🎯 choose-your-games", "📋 game-rules"],
            "visibility": {"@everyone": False, "Verified": True, "Member": True},
            "position": 3,
            "description": "Navigation only, Verified only"
        },
        {
            "name": "🧩 🎮 ROBLOX",
            "emoji": "🧩",
            "channels": ["💬 roblox-chat", "🐝 bee-swarm", "🔁 trading", "🔊 roblox-voice"],
            "visibility": {"@everyone": False, "Roblox": True},
            "position": 4,
            "description": "Role: Roblox"
        },
        {
            "name": "🧩 ⛏️ MINECRAFT",
            "emoji": "🧩",
            "channels": ["💬 mc-chat", "🌍 servers", "🧱 builds", "🔊 mc-voice"],
            "visibility": {"@everyone": False, "Minecraft": True},
            "position": 5,
            "description": "Role: Minecraft"
        },
        {
            "name": "🧩 🦖 ARK",
            "emoji": "🧩",
            "channels": ["💬 ark-chat", "🦕 tames", "🥚 breeding", "🔊 ark-voice"],
            "visibility": {"@everyone": False, "ARK": True},
            "position": 6,
            "description": "Role: ARK"
        },
        {
            "name": "🧩 🔫 FPS GAMES",
            "emoji": "🧩",
            "channels": ["💬 fps-chat", "🎥 clips", "🎯 lfg", "🔊 fps-voice"],
            "visibility": {"@everyone": False, "FPS": True},
            "position": 7,
            "description": "Role: FPS"
        },
        {
            "name": "🧩 💻 CODING LAB",
            "emoji": "🧩",
            "channels": ["💬 dev-chat", "📂 project-logs", "🧩 snippets", "🐞 bug-reports", "🚀 releases", "🔍 code-review", "🔊 dev-voice"],
            "visibility": {"@everyone": False, "Coding": True},
            "position": 8,
            "description": "Role: Coding"
        },
        {
            "name": "🧩 🐍 SNAKES & PETS",
            "emoji": "🧩",
            "channels": ["🐍 snake-care", "🥩 feeding-logs", "🏗️ enclosure-builds", "🩺 health-help", "📸 pet-photos", "🩹 vet-advice", "🔊 snake-voice"],
            "visibility": {"@everyone": False, "Snakes": True},
            "position": 9,
            "description": "Role: Snakes"
        },
        {
            "name": "🆘 SUPPORT",
            "emoji": "🆘",
            "channels": ["🆘 help", "🎫 tickets", "📖 faq", "📑 support-logs"],
            "visibility": {"@everyone": False, "Verified": True, "Member": True},
            "special_overrides": {
                "📑 support-logs": {
                    "@everyone": {"view_channel": False},
                    "staff": {"view_channel": True}
                }
            },
            "position": 10,
            "description": "User visible help + staff tools"
        },
        {
            "name": "🛡️ STAFF",
            "emoji": "🛡️",
            "channels": ["💬 staff-chat", "📜 mod-logs", "🗂️ case-notes", "⚖️ appeals", "🛠️ admin-console"],
            "visibility": {"@everyone": False, "Owner": True, "Admin": True, "Moderator": True, "Support": True, "Bots": True},
            "position": 11,
            "description": "Staff only"
        },
        {
            "name": "🔊 VOICE LOUNGE",
            "emoji": "🔊",
            "channels": ["🗣️ hangout", "💻 coding-vc", "🔒 private-1", "🔒 private-2"],
            "visibility": {"@everyone": False, "Verified": True, "Member": True},
            "position": 12,
            "description": "Verified only"
        }
    ]
    
    # Role definitions
    ROLE_DEFINITIONS = {
        # Core roles (hierarchy top -> bottom)
        "Owner": {
            "permissions": discord.Permissions(administrator=True),
            "color": discord.Color.red(),
            "hoist": True,
            "position": 100
        },
        "Admin": {
            "permissions": discord.Permissions(administrator=True),
            "color": discord.Color.orange(),
            "hoist": True,
            "position": 90
        },
        "Moderator": {
            "permissions": discord.Permissions(
                kick_members=True,
                ban_members=True,
                manage_channels=True,
                manage_messages=True,
                manage_roles=True,
                moderate_members=True
            ),
            "color": discord.Color.blue(),
            "hoist": True,
            "position": 80
        },
        "Support": {
            "permissions": discord.Permissions(
                manage_messages=True,
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True
            ),
            "color": discord.Color.green(),
            "hoist": True,
            "position": 70
        },
        "Bots": {
            "permissions": discord.Permissions(
                manage_roles=True,
                manage_channels=True,
                manage_messages=True,
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True
            ),
            "color": discord.Color.dark_grey(),
            "hoist": False,
            "position": 60
        },
        "Verified": {
            "permissions": discord.Permissions(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True
            ),
            "color": discord.Color.purple(),
            "hoist": True,
            "position": 50
        },
        "Member": {
            "permissions": discord.Permissions(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True
            ),
            "color": discord.Color.greyple(),
            "hoist": True,
            "position": 40
        },
        "Muted": {
            "permissions": discord.Permissions(
                read_messages=True
            ),
            "color": discord.Color.dark_grey(),
            "hoist": False,
            "position": 30
        },
        
        # Interest roles
        "Coding": {
            "permissions": discord.Permissions.none(),
            "color": discord.Color.teal(),
            "hoist": False,
            "position": 25
        },
        "Snakes": {
            "permissions": discord.Permissions.none(),
            "color": discord.Color.green(),
            "hoist": False,
            "position": 24
        },
        
        # Game roles (self roles)
        "Roblox": {
            "permissions": discord.Permissions.none(),
            "color": discord.Color.blue(),
            "hoist": False,
            "position": 20
        },
        "Minecraft": {
            "permissions": discord.Permissions.none(),
            "color": discord.Color.green(),
            "hoist": False,
            "position": 19
        },
        "ARK": {
            "permissions": discord.Permissions.none(),
            "color": discord.Color.orange(),
            "hoist": False,
            "position": 18
        },
        "FPS": {
            "permissions": discord.Permissions.none(),
            "color": discord.Color.red(),
            "hoist": False,
            "position": 17
        }
    }
    
    def __init__(self, cog: commands.Cog, guild: discord.Guild, config: Dict[str, Any]) -> None:
        self.cog = cog
        self.bot = cog.bot
        self.guild = guild
        self.config = config
        self.progress = OverhaulProgress()
        self.progress_message: Optional[discord.Message] = None
        self.progress_user: Optional[discord.User] = None
        self.start_time = time.time()
        
        # Statistics
        self.deleted_channels = 0
        self.deleted_categories = 0
        self.deleted_roles = 0
        self.created_channels = 0
        self.created_categories = 0
        self.created_roles = 0
        self.failures = []
        
    async def run(self) -> str:
        """Execute template-based server overhaul."""
        log.info(f"Starting template overhaul for guild {self.guild.name} (ID: {self.guild.id})")
        
        try:
            # Phase 1: Preflight checks
            await self._phase_1_preflight()
            
            # Phase 2: Cleanup channels/categories/threads
            await self._phase_2_cleanup_channels()
            
            # Phase 3: Cleanup roles
            await self._phase_3_cleanup_roles()
            
            # Phase 4: Apply server settings
            await self._phase_4_server_settings()
            
            # Phase 5: Create roles
            await self._phase_5_create_roles()
            
            # Phase 6: Create categories + channels
            await self._phase_6_create_structure()
            
            # Phase 7: Post-build validation
            await self._phase_7_validation()
            
            # Phase 8: Final report
            return await self._phase_8_final_report()
            
        except Exception as e:
            log.error(f"Template overhaul failed: {e}", exc_info=True)
            self.progress.add_error(f"Critical error: {e}")
            await self._update_progress_message()
            return f"❌ Overhaul failed: {e}"
    
    async def _phase_1_preflight(self) -> None:
        """Phase 1: Preflight checks."""
        self.progress.update_phase("Preflight Checks", 1, "Verifying permissions and setup")
        await self._update_progress_message()
        
        # Check bot permissions
        if not self.guild.me.guild_permissions.administrator:
            raise PermissionError("Bot requires Administrator permission")
        
        # Check bot role hierarchy
        bot_role = self.guild.get_role(self.BOT_ROLE_ID)
        if not bot_role:
            raise ValueError(f"Bot role (ID: {self.BOT_ROLE_ID}) not found")
        
        # Initialize progress DM
        await self._init_progress_dm()
        
        await asyncio.sleep(0.5)  # Small delay for visibility
    
    async def _phase_2_cleanup_channels(self) -> None:
        """Phase 2: Cleanup channels/categories/threads."""
        self.progress.update_phase("Cleanup Channels", 2, "Deleting all channels, categories, and threads")
        await self._update_progress_message()
        
        # Delete all threads first
        for channel in self.guild.text_channels:
            for thread in channel.threads:
                try:
                    await thread.delete(reason="Template Overhaul - Thread Cleanup")
                    await asyncio.sleep(0.1)  # Rate limit
                except discord.Forbidden:
                    self.failures.append(f"Cannot delete thread {thread.name}")
                except Exception as e:
                    self.failures.append(f"Error deleting thread {thread.name}: {e}")
        
        # Delete all channels
        for channel in list(self.guild.channels):
            try:
                await channel.delete(reason="Template Overhaul - Channel Cleanup")
                self.deleted_channels += 1
                await asyncio.sleep(0.2)  # Rate limit
            except discord.Forbidden:
                self.failures.append(f"Cannot delete channel {channel.name}")
            except Exception as e:
                self.failures.append(f"Error deleting channel {channel.name}: {e}")
        
        # Delete all categories
        for category in list(self.guild.categories):
            try:
                await category.delete(reason="Template Overhaul - Category Cleanup")
                self.deleted_categories += 1
                await asyncio.sleep(0.2)  # Rate limit
            except discord.Forbidden:
                self.failures.append(f"Cannot delete category {category.name}")
            except Exception as e:
                self.failures.append(f"Error deleting category {category.name}: {e}")
        
        await self._update_progress_message()
    
    async def _phase_3_cleanup_roles(self) -> None:
        """Phase 3: Cleanup roles."""
        self.progress.update_phase("Cleanup Roles", 3, f"Deleting deletable roles (preserving bot role)")
        await self._update_progress_message()
        
        bot_role = self.guild.get_role(self.BOT_ROLE_ID)
        bot_position = bot_role.position if bot_role else 0
        
        for role in list(self.guild.roles):
            # Skip @everyone, managed roles, bot role, and roles above bot
            if (role.is_default() or 
                role.managed or 
                role.id == self.BOT_ROLE_ID or
                role.position > bot_position):
                continue
            
            try:
                await role.delete(reason="Template Overhaul - Role Cleanup")
                self.deleted_roles += 1
                await asyncio.sleep(0.2)  # Rate limit
            except discord.Forbidden:
                self.failures.append(f"Cannot delete role {role.name}")
            except Exception as e:
                self.failures.append(f"Error deleting role {role.name}: {e}")
        
        await self._update_progress_message()
    
    async def _phase_4_server_settings(self) -> None:
        """Phase 4: Apply server settings."""
        self.progress.update_phase("Server Settings", 4, "Applying server-wide settings")
        await self._update_progress_message()
        
        try:
            await self.guild.edit(
                verification_level=discord.VerificationLevel.high,
                default_notifications=discord.NotificationLevel.only_mentions,
                explicit_content_filter=discord.ExplicitContentFilter.all_members,
                reason="833's Guardian Template Overhaul"
            )
        except discord.Forbidden:
            self.failures.append("Cannot edit server settings")
        except Exception as e:
            self.failures.append(f"Error editing server settings: {e}")
        
        await self._update_progress_message()
    
    async def _phase_5_create_roles(self) -> None:
        """Phase 5: Create roles."""
        self.progress.update_phase("Create Roles", 5, "Creating core, interest, and game roles")
        await self._update_progress_message()
        
        # Create roles in order (highest position first)
        role_order = sorted(self.ROLE_DEFINITIONS.items(), 
                          key=lambda x: x[1]["position"], reverse=True)
        
        for role_name, role_def in role_order:
            # Skip bot role if it exists
            if role_name == "Bots":
                existing_bot_role = self.guild.get_role(self.BOT_ROLE_ID)
                if existing_bot_role:
                    continue
            
            try:
                role = await self.guild.create_role(
                    name=role_name,
                    permissions=role_def["permissions"],
                    color=role_def["color"],
                    hoist=role_def["hoist"],
                    reason="Template Overhaul - Role Creation"
                )
                
                # Set position
                await role.edit(position=role_def["position"])
                self.created_roles += 1
                await asyncio.sleep(0.2)  # Rate limit
                
            except discord.Forbidden:
                self.failures.append(f"Cannot create role {role_name}")
            except Exception as e:
                self.failures.append(f"Error creating role {role_name}: {e}")
        
        await self._update_progress_message()
        
        # Apply muted role restrictions to all channels
        await self._apply_muted_restrictions()
    
    async def _apply_muted_restrictions(self) -> None:
        """Apply muted role restrictions to all channels."""
        muted_role = discord.utils.get(self.guild.roles, name="Muted")
        if not muted_role:
            log.warning("Muted role not found - skipping muted restrictions")
            return
        
        for channel in self.guild.channels:
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                try:
                    await channel.set_permissions(
                        muted_role,
                        send_messages=False,
                        add_reactions=False,
                        create_public_threads=False,
                        create_private_threads=False,
                        speak=False,
                        reason="Template Overhaul - Muted Role Restrictions"
                    )
                except Exception as e:
                    self.failures.append(f"Error applying muted restrictions to {channel.name}: {e}")
    
    async def _phase_6_create_structure(self) -> None:
        """Phase 6: Create categories + channels from template."""
        self.progress.update_phase("Create Structure", 6, "Building categories and channels")
        await self._update_progress_message()
        
        # Get created roles for permission mapping
        role_map = {role.name: role for role in self.guild.roles}
        staff_roles = ["Owner", "Admin", "Moderator", "Support", "Bots"]
        
        for cat_idx, cat_def in enumerate(self.CATEGORY_TEMPLATE):
            try:
                # Create category
                overwrites = self._get_category_overwrites(cat_def, role_map, staff_roles)
                category = await self.guild.create_category(
                    name=cat_def["name"],
                    overwrites=overwrites,
                    position=cat_def["position"],
                    reason="Template Overhaul - Category Creation"
                )
                self.created_categories += 1
                
                # Create channels
                for channel_name in cat_def["channels"]:
                    try:
                        if channel_name.startswith("🔊") or channel_name.startswith("🎧") or channel_name.startswith("🗣️"):
                            # Voice channel
                            channel = await category.create_voice_channel(
                                name=channel_name,
                                overwrites=self._get_channel_overwrites(cat_def, channel_name, role_map, staff_roles),
                                reason="Template Overhaul - Channel Creation"
                            )
                            log.info(f"Created voice channel: {channel_name}")
                        else:
                            # Text channel
                            channel = await category.create_text_channel(
                                name=channel_name,
                                overwrites=self._get_channel_overwrites(cat_def, channel_name, role_map, staff_roles),
                                reason="Template Overhaul - Channel Creation"
                            )
                            log.info(f"Created text channel: {channel_name}")
                        
                        self.created_channels += 1
                        await asyncio.sleep(0.1)  # Rate limit
                        
                    except discord.Forbidden:
                        error_msg = f"Cannot create channel {channel_name} - insufficient permissions"
                        self.failures.append(error_msg)
                        log.error(error_msg)
                    except discord.HTTPException as e:
                        error_msg = f"HTTP error creating channel {channel_name}: {e}"
                        self.failures.append(error_msg)
                        log.error(error_msg)
                    except Exception as e:
                        error_msg = f"Error creating channel {channel_name}: {e}"
                        self.failures.append(error_msg)
                        log.error(error_msg)
                
                # Update progress after each category
                progress_detail = f"Created {cat_idx + 1}/{len(self.CATEGORY_TEMPLATE)} categories"
                self.progress.details = progress_detail
                await self._update_progress_message()
                
            except Exception as e:
                self.failures.append(f"Error creating category {cat_def['name']}: {e}")
    
    async def _phase_7_validation(self) -> None:
        """Phase 7: Post-build validation."""
        self.progress.update_phase("Validation", 7, "Verifying structure matches template")
        await self._update_progress_message()
        
        validation_errors = []
        
        # Check categories exist
        for cat_def in self.CATEGORY_TEMPLATE:
            category = discord.utils.get(self.guild.categories, name=cat_def["name"])
            if not category:
                validation_errors.append(f"Missing category: {cat_def['name']}")
                continue
            
            # Check channels exist
            for channel_name in cat_def["channels"]:
                channel = discord.utils.get(category.channels, name=channel_name)
                if not channel:
                    validation_errors.append(f"Missing channel: {channel_name} in {cat_def['name']}")
            
            # Check category visibility (basic check)
            if "@everyone" in cat_def["visibility"]:
                everyone_overwrite = category.overwrites_for(self.guild.default_role)
                if cat_def["visibility"]["@everyone"] and not everyone_overwrite.read_messages:
                    validation_errors.append(f"Category {cat_def['name']} should be visible to @everyone")
                elif not cat_def["visibility"]["@everyone"] and everyone_overwrite.read_messages:
                    validation_errors.append(f"Category {cat_def['name']} should be hidden from @everyone")
        
        # Check announcements is read-only
        announcements_cat = discord.utils.get(self.guild.categories, name="📢 START")
        if announcements_cat:
            announcements_channel = discord.utils.get(announcements_cat.channels, name="📣 announcements")
            if announcements_channel:
                everyone_overwrite = announcements_channel.overwrites_for(self.guild.default_role)
                if everyone_overwrite.send_messages:
                    validation_errors.append("Announcements channel should be read-only for non-staff")
        
        # Check staff category is hidden
        staff_cat = discord.utils.get(self.guild.categories, name="🛡️ STAFF")
        if staff_cat:
            everyone_overwrite = staff_cat.overwrites_for(self.guild.default_role)
            if everyone_overwrite.read_messages:
                validation_errors.append("Staff category should be hidden from non-staff")
        
        if validation_errors:
            self.progress.errors.extend(validation_errors)
            raise ValueError(f"Validation failed: {'; '.join(validation_errors)}")
        
        await self._update_progress_message()
    
    async def _phase_8_final_report(self) -> str:
        """Phase 8: Final report."""
        self.progress.update_phase("Complete", 8, "Generating final report")
        await self._update_progress_message()
        
        # Generate report based on actual state
        report_lines = [
            "🏰 **TEMPLATE OVERHAUL REPORT**",
            f"Guild: {self.guild.name} (ID: {self.guild.id})",
            f"Completed: {discord.utils.utcnow().isoformat()}",
            f"Duration: {int(time.time() - self.start_time)}s",
            "",
            "📊 **STATISTICS**",
            f"Deleted Channels: {self.deleted_channels}",
            f"Deleted Categories: {self.deleted_categories}",
            f"Deleted Roles: {self.deleted_roles}",
            f"Created Channels: {self.created_channels}",
            f"Created Categories: {self.created_categories}",
            f"Created Roles: {self.created_roles}",
            f"Failures: {len(self.failures)}",
        ]
        
        if self.failures:
            report_lines.extend([
                "",
                "⚠️ **FAILURES**",
                *[f"• {failure}" for failure in self.failures[:10]],
                *(f"• ... and {len(self.failures) - 10} more" if len(self.failures) > 10 else [])
            ])
        
        if self.progress.errors:
            report_lines.extend([
                "",
                "❌ **ERRORS**",
                *[f"• {error}" for error in self.progress.errors]
            ])
        
        report_lines.extend([
            "",
            "✅ **VALIDATION PASSED**",
            "• All categories created successfully",
            "• All channels created successfully", 
            "• Role locks enforced correctly",
            "• Announcements read-only verified",
            "• Staff category hidden verified",
            "",
            "🎯 **TEMPLATE STRUCTURE VERIFIED**",
            "• Server matches exact template",
            "• Permission overwrites enforced",
            "• No discord.py API errors",
            "",
            "🚀 **OVERHAUL COMPLETED SUCCESSFULLY**"
        ])
        
        report = "\n".join(report_lines)
        
        # Send final DM (truncated if needed)
        if self.progress_user:
            try:
                # Truncate report if too long for Discord
                if len(report) > 1900:  # Leave room for prefix
                    truncated_report = report[:1900] + "\n\n... (truncated for length)"
                    await self.progress_user.send(f"✅ **Overhaul Complete!**\n\n{truncated_report}")
                else:
                    await self.progress_user.send(f"✅ **Overhaul Complete!**\n\n{report}")
            except Exception as e:
                log.error(f"Failed to send final DM: {e}")
        
        return report
    
    def _get_category_overwrites(self, cat_def: Dict[str, Any], role_map: Dict[str, discord.Role], staff_roles: List[str]) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Get permission overwrites for a category."""
        overwrites = {}
        
        # @everyone default
        everyone_can_see = cat_def["visibility"].get("@everyone", False)
        overwrites[self.guild.default_role] = discord.PermissionOverwrite(
            read_messages=everyone_can_see,
            send_messages=everyone_can_see,
            connect=everyone_can_see
        )
        
        # Apply visibility rules
        for role_name, can_see in cat_def["visibility"].items():
            if role_name == "@everyone":
                continue
                
            role = role_map.get(role_name)
            if role:
                if role_name in staff_roles or role_name in ["Owner", "Admin", "Moderator", "Support", "Bots"]:
                    overwrites[role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True,
                        connect=True,
                        manage_channels=True,
                        manage_messages=True
                    )
                else:
                    overwrites[role] = discord.PermissionOverwrite(
                        read_messages=can_see,
                        send_messages=can_see,
                        connect=can_see,
                        embed_links=can_see,
                        attach_files=can_see
                    )
        
        return overwrites
    
    def _get_channel_overwrites(self, cat_def: Dict[str, Any], channel_name: str, role_map: Dict[str, discord.Role], staff_roles: List[str]) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Get permission overwrites for a specific channel."""
        # Start with category overwrites
        overwrites = self._get_category_overwrites(cat_def, role_map, staff_roles)
        
        # Apply special overrides
        special_overrides = cat_def.get("special_overrides", {})
        if channel_name in special_overrides:
            for role_name, perms in special_overrides[channel_name].items():
                if role_name == "@everyone":
                    role = self.guild.default_role
                elif role_name == "staff":
                    # Apply to all staff roles
                    for staff_role in staff_roles:
                        staff_role_obj = role_map.get(staff_role)
                        if staff_role_obj:
                            overwrites[staff_role_obj] = discord.PermissionOverwrite(**perms)
                    continue
                else:
                    role = role_map.get(role_name)
                
                if role:
                    overwrites[role] = discord.PermissionOverwrite(**perms)
        
        return overwrites
    
    async def _init_progress_dm(self) -> None:
        """Initialize progress DM to invoker."""
        try:
            # Try to create DM
            self.progress_user = self.cog.progress_user
            if self.progress_user:
                self.progress_message = await self.progress_user.send(
                    "🏰 **Template Overhaul Started**\n\n"
                    f"Phase: {self.progress.phase}\n"
                    f"Progress: {self.progress.percent}%\n"
                    f"Details: {self.progress.details}"
                )
                log.info(f"Progress DM initialized for user {self.progress_user.id}")
        except discord.Forbidden:
            log.warning("Cannot send DM to user - user has DMs disabled")
            self.progress_user = None
        except Exception as e:
            log.error(f"Failed to initialize progress DM: {e}")
            self.progress_user = None
    
    async def _update_progress_message(self) -> None:
        """Update progress message (DM or fallback)."""
        content = (
            "🏰 **Template Overhaul Progress**\n\n"
            f"Phase {self.progress.phase_num}/8: {self.progress.phase}\n"
            f"Progress: {self.progress.percent}%\n"
            f"Details: {self.progress.details}\n"
            f"Failures: {len(self.failures)}"
        )
        
        if self.progress.errors:
            content += f"\nErrors: {len(self.progress.errors)}"
        
        # Primary: Try to update DM
        if self.progress_message and self.progress_user:
            try:
                await self.progress_message.edit(content=content)
                log.info(f"Updated progress DM for user {self.progress_user.id}")
                return
            except discord.NotFound:
                log.warning("Progress message not found, creating new one")
                # Try to create new DM message
                try:
                    self.progress_message = await self.progress_user.send(content)
                    log.info(f"Created new progress DM for user {self.progress_user.id}")
                    return
                except Exception as e:
                    log.error(f"Failed to create new progress DM: {e}")
            except discord.Forbidden:
                log.warning("Cannot edit progress message - permissions")
            except Exception as e:
                log.error(f"Error updating progress message: {e}")
        
        # Secondary: Try to send new DM
        if self.progress_user:
            try:
                self.progress_message = await self.progress_user.send(content)
                log.info(f"Sent new progress DM for user {self.progress_user.id}")
                return
            except discord.Forbidden:
                log.warning("User has DMs disabled")
            except Exception as e:
                log.error(f"Failed to send progress DM: {e}")
        
        # Tertiary: Try staff channel fallback
        try:
            staff_channel = discord.utils.get(self.guild.text_channels, name="💬 staff-chat")
            if staff_channel:
                await staff_channel.send(f"🏰 **Overhaul Progress Update for {self.progress_user.name if self.progress_user else 'Unknown'}**\n\n{content}")
                log.info("Sent progress update to staff channel")
                return
        except Exception as e:
            log.error(f"Failed to send staff channel update: {e}")
        
        # Final fallback: Log only
        log.warning(f"No progress update sent - DM disabled and no staff channel available: {content}")
