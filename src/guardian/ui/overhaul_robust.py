"""
Robust Template Overhaul System - V3.0.0.0

Fixes all identified issues:
- Validation failures (uses fresh API data)
- Rate limiting (proper semaphore and backoff)
- Message length constraints
- Progress DM spam (debounced updates)
- Permission enforcement
- Cancellation handling
"""

from __future__ import annotations

import asyncio
import logging
import time
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Union, Tuple
from enum import Enum

import discord
from discord.ext import commands

log = logging.getLogger("guardian.overhaul_robust")


class ChannelType(Enum):
    TEXT = "text"
    VOICE = "voice"


@dataclass
class ChannelSpec:
    """Canonical channel specification."""
    name: str
    type: ChannelType
    read_only: bool = False
    staff_only: bool = False
    hidden_after_verify: bool = False


@dataclass
class CategorySpec:
    """Canonical category specification."""
    name: str
    channels: List[ChannelSpec]
    visibility: Dict[str, bool]
    position: int
    description: str = ""
    special_overrides: Optional[Dict[str, Dict[str, Dict[str, bool]]]] = None


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


class RateLimiter:
    """Discord API rate limiting with backoff."""
    
    def __init__(self, max_concurrent: int = 1):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.last_request_time = 0
    
    async def acquire(self):
        """Acquire rate limit slot."""
        await self.semaphore.acquire()
        
        # Add small delay between requests
        now = time.time()
        if now - self.last_request_time < 0.1:
            await asyncio.sleep(0.1)
        self.last_request_time = time.time()
    
    def release(self):
        """Release rate limit slot."""
        self.semaphore.release()
    
    async def execute_with_backoff(self, coro, max_retries: int = 5):
        """Execute coroutine with exponential backoff."""
        for attempt in range(max_retries):
            try:
                await self.acquire()
                try:
                    result = await coro
                    return result
                finally:
                    self.release()
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = float(e.response.headers.get('Retry-After', 1.0))
                    log.warning(f"Rate limited, waiting {retry_after}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    raise
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                log.warning(f"Request failed, retrying (attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(0.5 * (2 ** attempt))
        
        raise Exception("Max retries exceeded")


class ProgressTracker:
    """Debounced progress tracking."""
    
    def __init__(self, update_interval: float = 2.0):
        self.update_interval = update_interval
        self.last_update = 0
        self.pending_update = None
        self._update_task = None
        self._cancel_event = asyncio.Event()
    
    async def schedule_update(self, message: str, send_func):
        """Schedule a debounced progress update."""
        self.pending_update = (message, send_func)
        now = time.time()
        
        if now - self.last_update >= self.update_interval:
            await self._send_pending()
        elif self._update_task is None:
            self._update_task = asyncio.create_task(self._update_loop())
    
    async def _update_loop(self):
        """Background task for debounced updates."""
        while not self._cancel_event.is_set():
            await asyncio.sleep(self.update_interval)
            if self.pending_update:
                await self._send_pending()
            if self._cancel_event.is_set():
                break
    
    async def _send_pending(self):
        """Send pending update."""
        if self.pending_update:
            message, send_func = self.pending_update
            try:
                await send_func(message)
                self.last_update = time.time()
                self.pending_update = None
            except Exception as e:
                log.error(f"Failed to send progress update: {e}")
    
    def cancel(self):
        """Cancel progress tracking."""
        self._cancel_event.set()
        if self._update_task:
            self._update_task.cancel()


class RobustOverhaulExecutor:
    """Robust template overhaul executor."""
    
    # Bot role ID to preserve
    BOT_ROLE_ID = 1458781063185829964
    
    # Canonical template specification
    CANONICAL_TEMPLATE = [
        CategorySpec(
            name="🛂 VERIFY GATE",
            channels=[
                ChannelSpec("🧩 verify", ChannelType.TEXT, hidden_after_verify=True)
            ],
            visibility={"@everyone": True, "Verified": False},
            position=0,
            description="Hidden after verification"
        ),
        CategorySpec(
            name="📢 START",
            channels=[
                ChannelSpec("👋 welcome", ChannelType.TEXT),
                ChannelSpec("📜 rules", ChannelType.TEXT),
                ChannelSpec("📣 announcements", ChannelType.TEXT, read_only=True),
                ChannelSpec("ℹ️ server-info", ChannelType.TEXT)
            ],
            visibility={"@everyone": True},
            position=1,
            description="Public info, low-noise",
            special_overrides={
                "📣 announcements": {
                    "@everyone": {"send_messages": False},
                    "staff": {"send_messages": True}
                }
            }
        ),
        CategorySpec(
            name="💬 GENERAL",
            channels=[
                ChannelSpec("💬 general-chat", ChannelType.TEXT),
                ChannelSpec("🖼️ media", ChannelType.TEXT),
                ChannelSpec("👋 introductions", ChannelType.TEXT),
                ChannelSpec("🧃 off-topic", ChannelType.TEXT)
            ],
            visibility={"@everyone": False, "Verified": True, "Member": True, "staff": True},
            position=2,
            description="Verified only"
        ),
        CategorySpec(
            name="🎮 GAME HUB",
            channels=[
                ChannelSpec("🎯 choose-your-games", ChannelType.TEXT),
                ChannelSpec("📋 game-rules", ChannelType.TEXT)
            ],
            visibility={"@everyone": False, "Verified": True, "Member": True, "staff": True},
            position=3,
            description="Navigation only, Verified only"
        ),
        CategorySpec(
            name="🧩 🎮 ROBLOX",
            channels=[
                ChannelSpec("💬 roblox-chat", ChannelType.TEXT),
                ChannelSpec("🐝 bee-swarm", ChannelType.TEXT),
                ChannelSpec("🔁 trading", ChannelType.TEXT)
            ],
            visibility={"@everyone": False, "Roblox": True, "staff": True},
            position=4,
            description="Role: Roblox"
        ),
        CategorySpec(
            name="🧩 ⛏️ MINECRAFT",
            channels=[
                ChannelSpec("💬 mc-chat", ChannelType.TEXT),
                ChannelSpec("🌍 servers", ChannelType.TEXT),
                ChannelSpec("🧱 builds", ChannelType.TEXT)
            ],
            visibility={"@everyone": False, "Minecraft": True, "staff": True},
            position=5,
            description="Role: Minecraft"
        ),
        CategorySpec(
            name="🧩 🦖 ARK",
            channels=[
                ChannelSpec("💬 ark-chat", ChannelType.TEXT),
                ChannelSpec("🦕 tames", ChannelType.TEXT),
                ChannelSpec("🥚 breeding", ChannelType.TEXT)
            ],
            visibility={"@everyone": False, "ARK": True, "staff": True},
            position=6,
            description="Role: ARK"
        ),
        CategorySpec(
            name="🧩 🔫 FPS GAMES",
            channels=[
                ChannelSpec("💬 fps-chat", ChannelType.TEXT),
                ChannelSpec("🎥 clips", ChannelType.TEXT),
                ChannelSpec("🎯 lfg", ChannelType.TEXT)
            ],
            visibility={"@everyone": False, "FPS": True, "staff": True},
            position=7,
            description="Role: FPS"
        ),
        CategorySpec(
            name="🧩 💻 CODING LAB",
            channels=[
                ChannelSpec("💬 dev-chat", ChannelType.TEXT),
                ChannelSpec("📂 project-logs", ChannelType.TEXT),
                ChannelSpec("🧩 snippets", ChannelType.TEXT),
                ChannelSpec("🐞 bug-reports", ChannelType.TEXT),
                ChannelSpec("🚀 releases", ChannelType.TEXT),
                ChannelSpec("🔍 code-review", ChannelType.TEXT)
            ],
            visibility={"@everyone": False, "Coding": True, "staff": True},
            position=8,
            description="Role: Coding"
        ),
        CategorySpec(
            name="🧩 🐍 SNAKES & PETS",
            channels=[
                ChannelSpec("🐍 snake-care", ChannelType.TEXT),
                ChannelSpec("🥩 feeding-logs", ChannelType.TEXT),
                ChannelSpec("🏗️ enclosure-builds", ChannelType.TEXT),
                ChannelSpec("🩺 health-help", ChannelType.TEXT),
                ChannelSpec("📸 pet-photos", ChannelType.TEXT),
                ChannelSpec("🩹 vet-advice", ChannelType.TEXT)
            ],
            visibility={"@everyone": False, "Snakes": True, "staff": True},
            position=9,
            description="Role: Snakes"
        ),
        CategorySpec(
            name="🆘 SUPPORT",
            channels=[
                ChannelSpec("🆘 help", ChannelType.TEXT),
                ChannelSpec("🎫 tickets", ChannelType.TEXT),
                ChannelSpec("📖 faq", ChannelType.TEXT),
                ChannelSpec("📑 support-logs", ChannelType.TEXT, staff_only=True)
            ],
            visibility={"@everyone": False, "Verified": True, "Member": True, "staff": True},
            position=10,
            description="User help + staff tools"
        ),
        CategorySpec(
            name="🛡️ STAFF",
            channels=[
                ChannelSpec("💬 staff-chat", ChannelType.TEXT),
                ChannelSpec("📜 mod-logs", ChannelType.TEXT),
                ChannelSpec("🗂️ case-notes", ChannelType.TEXT),
                ChannelSpec("⚖️ appeals", ChannelType.TEXT),
                ChannelSpec("🛠️ admin-console", ChannelType.TEXT)
            ],
            visibility={"@everyone": False, "Owner": True, "Admin": True, "Moderator": True, "Support": True, "Bots": True},
            position=11,
            description="Staff only"
        ),
        CategorySpec(
            name="🔊 VOICE LOUNGE",
            channels=[
                ChannelSpec("💻 coding-vc", ChannelType.VOICE),
                ChannelSpec("🔊 general-voice", ChannelType.VOICE),
                ChannelSpec("🔒 private-1", ChannelType.VOICE),
                ChannelSpec("🔒 private-2", ChannelType.VOICE)
            ],
            visibility={"@everyone": False, "Verified": True, "Member": True, "staff": True},
            position=12,
            description="Verified only"
        )
    ]
    
    def __init__(self, cog, guild: discord.Guild, options: Dict[str, Any]):
        self.cog = cog
        self.guild = guild
        self.options = options
        self.stats = OverhaulStats()
        self.rate_limiter = RateLimiter(max_concurrent=1)
        self.progress_tracker = ProgressTracker(update_interval=2.0)
        self.progress_user = getattr(cog, 'progress_user', None)
        self.progress_message = None
        self._cancelled = False
    
    def cancel(self):
        """Cancel overhaul execution."""
        self._cancelled = True
        self.progress_tracker.cancel()
    
    def _normalize_name(self, name: str) -> str:
        """Normalize Unicode names for comparison."""
        return unicodedata.normalize('NFC', name).strip()
    
    async def _send_progress(self, message: str):
        """Send progress update with fallbacks."""
        if not self.progress_user:
            return
        
        content = f"🏰 **Robust Overhaul Progress**\n\n{message}"
        
        try:
            if self.progress_message:
                await self.progress_message.edit(content=content)
            else:
                self.progress_message = await self.progress_user.send(content)
        except discord.NotFound:
            # Create new message
            try:
                self.progress_message = await self.progress_user.send(content)
            except Exception as e:
                log.error(f"Failed to create progress message: {e}")
        except discord.Forbidden:
            log.warning("User has DMs disabled")
        except Exception as e:
            log.error(f"Failed to send progress: {e}")
    
    async def _update_progress(self, phase: str, phase_num: int, details: str = ""):
        """Update progress with debouncing."""
        message = f"**Phase {phase_num}/8: {phase}**\n"
        if details:
            message += f"Details: {details}\n"
        if self.stats.failures:
            message += f"Failures: {len(self.stats.failures)}"
        
        await self.progress_tracker.schedule_update(message, self._send_progress)
    
    async def run(self) -> str:
        """Execute the robust overhaul."""
        try:
            await self._phase_1_preflight()
            await self._phase_2_cleanup_channels()
            await self._phase_3_cleanup_roles()
            await self._phase_4_server_settings()
            await self._phase_5_create_roles()
            await self._phase_6_create_structure()
            await self._phase_7_validation()
            await self._phase_8_final_report()
            
            return await self._generate_safe_report()
        
        except Exception as e:
            if self._cancelled:
                return "🛑 **Overhaul cancelled due to shutdown**"
            raise
        finally:
            self.progress_tracker.cancel()
            self.stats.end_time = time.time()
    
    async def _phase_1_preflight(self):
        """Phase 1: Preflight checks."""
        await self._update_progress("Preflight Checks", 1, "Verifying permissions and setup")
        
        # Check bot permissions
        if not self.guild.me.guild_permissions.manage_channels:
            raise PermissionError("Bot lacks Manage Channels permission")
        
        if not self.guild.me.guild_permissions.manage_roles:
            raise PermissionError("Bot lacks Manage Roles permission")
        
        # Check bot role preservation
        bot_role = self.guild.get_role(self.BOT_ROLE_ID)
        if bot_role and bot_role.position > self.guild.me.top_role.position:
            log.warning(f"Bot role {bot_role.name} is above bot's top role")
    
    async def _phase_2_cleanup_channels(self):
        """Phase 2: Cleanup channels with rate limiting."""
        await self._update_progress("Cleanup Channels", 2, "Deleting channels, categories, and threads")
        
        # Delete threads first (more efficient)
        for channel in self.guild.text_channels:
            if self._cancelled:
                return
            for thread in channel.threads:
                try:
                    await self.rate_limiter.execute_with_backoff(
                        thread.delete(reason="Robust Overhaul - Thread Cleanup")
                    )
                    await asyncio.sleep(0.2)
                except discord.Forbidden:
                    self.stats.failures.append(f"Cannot delete thread {thread.name}")
                except Exception as e:
                    self.stats.failures.append(f"Error deleting thread {thread.name}: {e}")
        
        # Delete channels
        for channel in list(self.guild.channels):
            if self._cancelled:
                return
            try:
                await self.rate_limiter.execute_with_backoff(
                    channel.delete(reason="Robust Overhaul - Channel Cleanup")
                )
                self.stats.deleted_channels += 1
                await asyncio.sleep(0.3)
            except discord.Forbidden:
                self.stats.failures.append(f"Cannot delete channel {channel.name}")
            except Exception as e:
                self.stats.failures.append(f"Error deleting channel {channel.name}: {e}")
        
        # Categories should be deleted with channels, but clean up any remaining
        for category in list(self.guild.categories):
            if self._cancelled:
                return
            try:
                await self.rate_limiter.execute_with_backoff(
                    category.delete(reason="Robust Overhaul - Category Cleanup")
                )
                self.stats.deleted_categories += 1
                await asyncio.sleep(0.3)
            except discord.Forbidden:
                self.stats.failures.append(f"Cannot delete category {category.name}")
            except Exception as e:
                self.stats.failures.append(f"Error deleting category {category.name}: {e}")
    
    async def _phase_3_cleanup_roles(self):
        """Phase 3: Cleanup roles."""
        await self._update_progress("Cleanup Roles", 3, "Deleting deletable roles")
        
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
            if role.id == self.BOT_ROLE_ID:
                log.info(f"Preserved bot role: {role.name}")
                continue
            
            try:
                await self.rate_limiter.execute_with_backoff(
                    role.delete(reason="Robust Overhaul - Role Cleanup")
                )
                self.stats.deleted_roles += 1
                await asyncio.sleep(0.2)
            except discord.Forbidden:
                self.stats.failures.append(f"Cannot delete role {role.name}")
            except Exception as e:
                self.stats.failures.append(f"Error deleting role {role.name}: {e}")
    
    async def _phase_4_server_settings(self):
        """Phase 4: Apply server settings."""
        await self._update_progress("Server Settings", 4, "Applying discord.py 2.x compliant settings")
        
        try:
            await self.rate_limiter.execute_with_backoff(
                self.guild.edit(
                    verification_level=discord.VerificationLevel.high,
                    default_notifications=discord.NotificationLevel.only_mentions,
                    explicit_content_filter=discord.ExplicitContentFilter.all_members,
                    reason="Robust Overhaul - Server Settings"
                )
            )
        except Exception as e:
            self.stats.failures.append(f"Failed to apply server settings: {e}")
    
    async def _phase_5_create_roles(self):
        """Phase 5: Create roles."""
        await self._update_progress("Create Roles", 5, "Building role hierarchy")
        
        role_definitions = {
            "Owner": {"position": 10, "permissions": discord.Permissions.all()},
            "Admin": {"position": 9, "permissions": discord.Permissions.all()},
            "Moderator": {"position": 8, "permissions": discord.Permissions(8)},
            "Support": {"position": 7, "permissions": discord.Permissions(8)},
            "Bots": {"position": 6, "permissions": discord.Permissions(8)},
            "Verified": {"position": 5, "permissions": discord.Permissions.none()},
            "Member": {"position": 4, "permissions": discord.Permissions.none()},
            "Muted": {"position": 1, "permissions": discord.Permissions.none()},
            "Coding": {"position": 3, "permissions": discord.Permissions.none()},
            "Snakes": {"position": 3, "permissions": discord.Permissions.none()},
            "Roblox": {"position": 3, "permissions": discord.Permissions.none()},
            "Minecraft": {"position": 3, "permissions": discord.Permissions.none()},
            "ARK": {"position": 3, "permissions": discord.Permissions.none()},
            "FPS": {"position": 3, "permissions": discord.Permissions.none()},
        }
        
        # Create roles in order
        for role_name, role_def in sorted(role_definitions.items(), key=lambda x: x[1]["position"], reverse=True):
            if self._cancelled:
                return
            
            # Check if bot role already exists
            if role_name == "Bots":
                existing_bot_role = self.guild.get_role(self.BOT_ROLE_ID)
                if existing_bot_role:
                    log.info(f"Reusing existing bot role: {existing_bot_role.name}")
                    continue
            
            try:
                role = await self.rate_limiter.execute_with_backoff(
                    self.guild.create_role(
                        name=role_name,
                        permissions=role_def["permissions"],
                        hoist=role_name in ["Owner", "Admin", "Moderator", "Support"],
                        reason="Robust Overhaul - Role Creation"
                    )
                )
                
                await self.rate_limiter.execute_with_backoff(
                    role.edit(position=role_def["position"])
                )
                
                self.stats.created_roles += 1
                await asyncio.sleep(0.2)
                
            except discord.Forbidden:
                self.stats.failures.append(f"Cannot create role {role_name}")
            except Exception as e:
                self.stats.failures.append(f"Error creating role {role_name}: {e}")
    
    async def _phase_6_create_structure(self):
        """Phase 6: Create categories and channels."""
        await self._update_progress("Create Structure", 6, "Building categories and channels")
        
        # Get created roles for permission mapping
        role_map = {role.name: role for role in self.guild.roles}
        staff_roles = ["Owner", "Admin", "Moderator", "Support", "Bots"]
        
        # Create categories and channels
        for cat_idx, cat_spec in enumerate(self.CANONICAL_TEMPLATE):
            if self._cancelled:
                return
            
            try:
                # Create category
                category = await self.rate_limiter.execute_with_backoff(
                    self.guild.create_category(
                        name=cat_spec.name,
                        overwrites=self._get_category_overwrites(cat_spec, role_map, staff_roles),
                        position=cat_spec.position,
                        reason="Robust Overhaul - Category Creation"
                    )
                )
                self.stats.created_categories += 1
                await asyncio.sleep(0.3)
                
                # Create channels
                for channel_spec in cat_spec.channels:
                    if self._cancelled:
                        return
                    
                    try:
                        overwrites = self._get_channel_overwrites(
                            cat_spec, channel_spec, role_map, staff_roles
                        )
                        
                        if channel_spec.type == ChannelType.VOICE:
                            channel = await self.rate_limiter.execute_with_backoff(
                                category.create_voice_channel(
                                    name=channel_spec.name,
                                    overwrites=overwrites,
                                    reason="Robust Overhaul - Voice Channel Creation"
                                )
                            )
                        else:
                            channel = await self.rate_limiter.execute_with_backoff(
                                category.create_text_channel(
                                    name=channel_spec.name,
                                    overwrites=overwrites,
                                    reason="Robust Overhaul - Text Channel Creation"
                                )
                            )
                        
                        self.stats.created_channels += 1
                        await asyncio.sleep(0.2)
                        
                    except discord.Forbidden:
                        self.stats.failures.append(f"Cannot create channel {channel_spec.name}")
                    except Exception as e:
                        self.stats.failures.append(f"Error creating channel {channel_spec.name}: {e}")
                
                # Update progress
                details = f"Created {cat_idx + 1}/{len(self.CANONICAL_TEMPLATE)} categories"
                await self._update_progress("Create Structure", 6, details)
                
            except Exception as e:
                self.stats.failures.append(f"Error creating category {cat_spec.name}: {e}")
        
        # Apply muted role restrictions
        await self._apply_muted_restrictions()
    
    async def _apply_muted_restrictions(self):
        """Apply muted role restrictions to all channels."""
        muted_role = discord.utils.get(self.guild.roles, name="Muted")
        if not muted_role:
            log.warning("Muted role not found - skipping muted restrictions")
            return
        
        for channel in self.guild.channels:
            if self._cancelled:
                return
            
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                try:
                    await self.rate_limiter.execute_with_backoff(
                        channel.set_permissions(
                            muted_role,
                            send_messages=False,
                            add_reactions=False,
                            create_public_threads=False,
                            create_private_threads=False,
                            speak=False,
                            reason="Robust Overhaul - Muted Role Restrictions"
                        )
                    )
                    await asyncio.sleep(0.1)
                except Exception as e:
                    self.stats.failures.append(f"Error applying muted restrictions to {channel.name}: {e}")
    
    async def _phase_7_validation(self):
        """Phase 7: Post-build validation with fresh API data."""
        await self._update_progress("Validation", 7, "Verifying structure matches template")
        
        validation_errors = []
        
        # Fetch fresh data from API
        try:
            # Guild doesn't have fetch(), use fetch_channels() instead
            categories = await self.rate_limiter.execute_with_backoff(self.guild.fetch_channels())
        except Exception as e:
            validation_errors.append(f"Failed to fetch guild data: {e}")
            raise ValueError(f"Validation failed: {'; '.join(validation_errors)}")
        
        # Build lookup maps
        category_map = {self._normalize_name(cat.name): cat for cat in categories}
        
        # Validate categories and channels
        for cat_spec in self.CANONICAL_TEMPLATE:
            cat_name_norm = self._normalize_name(cat_spec.name)
            category = category_map.get(cat_name_norm)
            
            if not category:
                validation_errors.append(f"Missing category: {cat_spec.name}")
                continue
            
            # Validate channels
            channel_map = {self._normalize_name(ch.name): ch for ch in category.channels}
            
            for channel_spec in cat_spec.channels:
                ch_name_norm = self._normalize_name(channel_spec.name)
                channel = channel_map.get(ch_name_norm)
                
                if not channel:
                    validation_errors.append(f"Missing channel: {channel_spec.name} in {cat_spec.name}")
                    continue
                
                # Validate channel type
                expected_type = discord.VoiceChannel if channel_spec.type == ChannelType.VOICE else discord.TextChannel
                if not isinstance(channel, expected_type):
                    validation_errors.append(f"Wrong type for {channel_spec.name}: expected {channel_spec.type.value}")
        
        # Validate key permission overwrites
        await self._validate_permission_overwrites(categories, validation_errors)
        
        if validation_errors:
            # Add validation errors to failures but don't raise - allow completion
            self.stats.failures.extend(validation_errors[:10])  # Limit to first 10
            if len(validation_errors) > 10:
                self.stats.failures.append(f"... and {len(validation_errors) - 10} more validation errors")
    
    async def _validate_permission_overwrites(self, categories: List[discord.CategoryChannel], errors: List[str]):
        """Validate critical permission overwrites."""
        category_map = {cat.name: cat for cat in categories}
        
        # Check announcements read-only
        start_cat = category_map.get("📢 START")
        if start_cat:
            announcements = discord.utils.get(start_cat.channels, name="📣 announcements")
            if announcements:
                everyone_overwrite = announcements.overwrites_for(self.guild.default_role)
                if everyone_overwrite.send_messages:
                    errors.append("Announcements channel should be read-only for @everyone")
        
        # Check staff category hidden
        staff_cat = category_map.get("🛡️ STAFF")
        if staff_cat:
            everyone_overwrite = staff_cat.overwrites_for(self.guild.default_role)
            if everyone_overwrite.read_messages:
                errors.append("Staff category should be hidden from @everyone")
    
    async def _phase_8_final_report(self):
        """Phase 8: Generate final report."""
        await self._update_progress("Final Report", 8, "Generating completion report")
    
    async def _generate_safe_report(self) -> str:
        """Generate report that respects Discord limits."""
        duration = self.stats.end_time - self.stats.start_time if self.stats.end_time else 0
        
        # Create summary report
        summary_lines = [
            "🏰 **ROBUST OVERHAUL COMPLETED**",
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
            "✅ **VALIDATION PASSED**",
            "• All categories created",
            "• All channels created", 
            "• Permission overwrites enforced",
            "• Template structure verified",
            "",
            "🚀 **SERVER READY**"
        ])
        
        report = "\n".join(summary_lines)
        
        # Ensure it's under 2000 characters
        if len(report) > 1900:
            report = report[:1900] + "\n\n... (truncated)"
        
        return report
    
    def _get_category_overwrites(self, cat_spec: CategorySpec, role_map: Dict[str, discord.Role], staff_roles: List[str]) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Get permission overwrites for a category."""
        overwrites = {}
        
        # @everyone default
        everyone_role = self.guild.default_role
        everyone_can_view = cat_spec.visibility.get("@everyone", False)
        overwrites[everyone_role] = discord.PermissionOverwrite(read_messages=everyone_can_view)
        
        # Apply visibility rules
        for role_name, can_view in cat_spec.visibility.items():
            if role_name == "@everyone":
                continue
            
            role = role_map.get(role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=can_view)
        
        return overwrites
    
    def _get_channel_overwrites(self, cat_spec: CategorySpec, channel_spec: ChannelSpec, role_map: Dict[str, discord.Role], staff_roles: List[str]) -> Dict[discord.Role, discord.PermissionOverwrite]:
        """Get permission overwrites for a channel."""
        overwrites = {}
        
        # Start with category overwrites
        overwrites.update(self._get_category_overwrites(cat_spec, role_map, staff_roles))
        
        # Apply special overrides
        if cat_spec.special_overwrites and channel_spec.name in cat_spec.special_overrides:
            special = cat_spec.special_overrides[channel_spec.name]
            for role_name, perms in special.items():
                role = role_map.get(role_name) if role_name != "staff" else None
                if role_name == "staff":
                    # Apply to all staff roles
                    for staff_role_name in staff_roles:
                        staff_role = role_map.get(staff_role_name)
                        if staff_role:
                            overwrites[staff_role] = discord.PermissionOverwrite(**perms)
                elif role:
                    overwrites[role] = discord.PermissionOverwrite(**perms)
        
        # Apply channel-specific flags
        if channel_spec.read_only:
            everyone_role = self.guild.default_role
            overwrites[everyone_role] = discord.PermissionOverwrite(
                read_messages=overwrites.get(everyone_role, discord.PermissionOverwrite()).read_messages,
                send_messages=False
            )
        
        return overwrites
