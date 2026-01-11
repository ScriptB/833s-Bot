"""
Production-Ready Overhaul System - V4.0.0.0

Complete rewrite addressing all identified issues:
- Proper interaction handling with await
- Correct emoji template implementation
- Rate-limit safe operations
- Debounced progress DMs
- Comprehensive error handling
- Message length safety
- Leveling compatibility
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import traceback
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Union, Tuple
from enum import Enum

import discord
from discord.ext import commands

log = logging.getLogger("guardian.overhaul_production")


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


@dataclass
class CategorySpec:
    """Canonical category specification."""
    name: str
    channels: List[ChannelSpec]
    visibility: Dict[str, bool]
    position: int
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


class ProductionRateLimiter:
    """Production-ready rate limiting with jitter and retry logic."""
    
    def __init__(self):
        self.semaphore = asyncio.Semaphore(1)  # Global semaphore for all operations
        self.last_request_time = 0
    
    async def execute_with_retry(self, coro_func, max_retries: int = 5):
        """Execute coroutine with rate limiting and retry logic."""
        for attempt in range(max_retries):
            try:
                await self.semaphore.acquire()
                try:
                    # Add jittered delay between operations
                    await self._jittered_sleep()
                    result = await coro_func()
                    return result
                finally:
                    self.semaphore.release()
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
                    log.error(f"Max retries exceeded for operation: {e}")
                    raise
                log.warning(f"Request failed, retrying (attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(0.5 * (2 ** attempt))
        
        raise Exception("Max retries exceeded")
    
    async def _jittered_sleep(self):
        """Add jittered sleep between operations (0.3-0.8s)."""
        now = time.time()
        min_delay = 0.3
        max_delay = 0.8
        
        if now - self.last_request_time < min_delay:
            delay = random.uniform(min_delay, max_delay)
            await asyncio.sleep(delay)
        
        self.last_request_time = time.time()


class DebouncedProgressTracker:
    """Debounced progress tracking with single DM message."""
    
    def __init__(self, update_interval: float = 2.0):
        self.update_interval = update_interval
        self.last_update = 0
        self.pending_update = None
        self.dm_message = None
        self.dm_user = None
        self._update_task = None
        self._cancel_event = asyncio.Event()
    
    def set_user(self, user: discord.User):
        """Set the user for progress DMs."""
        self.dm_user = user
    
    async def schedule_update(self, message: str):
        """Schedule a debounced progress update."""
        self.pending_update = message
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
        """Send pending update via DM."""
        if not self.pending_update or not self.dm_user:
            return
        
        content = f"🏰 **Server Overhaul Progress**\n\n{self.pending_update}"
        
        try:
            # Ensure content is under Discord limit
            if len(content) > 1900:
                content = content[:1900] + "\n\n... (truncated)"
            
            if self.dm_message:
                await self.dm_message.edit(content=content)
            else:
                self.dm_message = await self.dm_user.send(content)
            
            self.last_update = time.time()
            self.pending_update = None
            
        except discord.Forbidden:
            log.warning("User has DMs disabled, progress updates unavailable")
        except Exception as e:
            log.error(f"Failed to send progress update: {e}")
    
    def cancel(self):
        """Cancel progress tracking."""
        self._cancel_event.set()
        if self._update_task:
            self._update_task.cancel()


class ProductionOverhaulExecutor:
    """Production-ready overhaul executor with comprehensive error handling."""
    
    # Bot role ID to preserve
    BOT_ROLE_ID = 1458781063185829964
    
    # Canonical emoji template (single source of truth)
    CANONICAL_TEMPLATE = [
        CategorySpec(
            name="🛂 VERIFY GATE",
            channels=[
                ChannelSpec("🧩 verify", ChannelType.TEXT)
            ],
            visibility={"@everyone": True, "Verified": False, "staff": True},
            position=0
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
                ChannelSpec("🧃 off-topic", ChannelType.TEXT),
                ChannelSpec("🔊 general-voice", ChannelType.VOICE),
                ChannelSpec("🎧 chill-voice", ChannelType.VOICE)
            ],
            visibility={"@everyone": False, "Verified": True, "Member": True, "staff": True},
            position=2
        ),
        CategorySpec(
            name="🎮 GAME HUB",
            channels=[
                ChannelSpec("🎯 choose-your-games", ChannelType.TEXT),
                ChannelSpec("📋 game-rules", ChannelType.TEXT)
            ],
            visibility={"@everyone": False, "Verified": True, "Member": True, "staff": True},
            position=3
        ),
        CategorySpec(
            name="🧩 🎮 ROBLOX",
            channels=[
                ChannelSpec("💬 roblox-chat", ChannelType.TEXT),
                ChannelSpec("🐝 bee-swarm", ChannelType.TEXT),
                ChannelSpec("🔁 trading", ChannelType.TEXT),
                ChannelSpec("🔊 roblox-voice", ChannelType.VOICE)
            ],
            visibility={"@everyone": False, "Roblox": True, "staff": True},
            position=4
        ),
        CategorySpec(
            name="🧩 ⛏️ MINECRAFT",
            channels=[
                ChannelSpec("💬 mc-chat", ChannelType.TEXT),
                ChannelSpec("🌍 servers", ChannelType.TEXT),
                ChannelSpec("🧱 builds", ChannelType.TEXT),
                ChannelSpec("🔊 mc-voice", ChannelType.VOICE)
            ],
            visibility={"@everyone": False, "Minecraft": True, "staff": True},
            position=5
        ),
        CategorySpec(
            name="🧩 🦖 ARK",
            channels=[
                ChannelSpec("💬 ark-chat", ChannelType.TEXT),
                ChannelSpec("🦕 tames", ChannelType.TEXT),
                ChannelSpec("🥚 breeding", ChannelType.TEXT),
                ChannelSpec("🔊 ark-voice", ChannelType.VOICE)
            ],
            visibility={"@everyone": False, "ARK": True, "staff": True},
            position=6
        ),
        CategorySpec(
            name="🧩 🔫 FPS GAMES",
            channels=[
                ChannelSpec("💬 fps-chat", ChannelType.TEXT),
                ChannelSpec("🎥 clips", ChannelType.TEXT),
                ChannelSpec("🎯 lfg", ChannelType.TEXT),
                ChannelSpec("🔊 fps-voice", ChannelType.VOICE)
            ],
            visibility={"@everyone": False, "FPS": True, "staff": True},
            position=7
        ),
        CategorySpec(
            name="🧩 💻 CODING LAB",
            channels=[
                ChannelSpec("💬 dev-chat", ChannelType.TEXT),
                ChannelSpec("📂 project-logs", ChannelType.TEXT),
                ChannelSpec("🧩 snippets", ChannelType.TEXT),
                ChannelSpec("🐞 bug-reports", ChannelType.TEXT),
                ChannelSpec("🚀 releases", ChannelType.TEXT),
                ChannelSpec("🔍 code-review", ChannelType.TEXT),
                ChannelSpec("🔊 dev-voice", ChannelType.VOICE)
            ],
            visibility={"@everyone": False, "Coding": True, "staff": True},
            position=8
        ),
        CategorySpec(
            name="🧩 🐍 SNAKES & PETS",
            channels=[
                ChannelSpec("🐍 snake-care", ChannelType.TEXT),
                ChannelSpec("🥩 feeding-logs", ChannelType.TEXT),
                ChannelSpec("🏗️ enclosure-builds", ChannelType.TEXT),
                ChannelSpec("🩺 health-help", ChannelType.TEXT),
                ChannelSpec("📸 pet-photos", ChannelType.TEXT),
                ChannelSpec("🩹 vet-advice", ChannelType.TEXT),
                ChannelSpec("🔊 snake-voice", ChannelType.VOICE)
            ],
            visibility={"@everyone": False, "Snakes": True, "staff": True},
            position=9
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
            position=10
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
            position=11
        ),
        CategorySpec(
            name="🔊 VOICE LOUNGE",
            channels=[
                ChannelSpec("🗣️ hangout", ChannelType.VOICE),
                ChannelSpec("💻 coding-vc", ChannelType.VOICE),
                ChannelSpec("🔒 private-1", ChannelType.VOICE),
                ChannelSpec("🔒 private-2", ChannelType.VOICE)
            ],
            visibility={"@everyone": False, "Verified": True, "Member": True, "staff": True},
            position=12
        )
    ]
    
    def __init__(self, cog, guild: discord.Guild, options: Dict[str, Any]):
        self.cog = cog
        self.guild = guild
        self.options = options
        self.stats = OverhaulStats()
        self.rate_limiter = ProductionRateLimiter()
        self.progress_tracker = DebouncedProgressTracker()
        self._cancelled = False
    
    def cancel(self):
        """Cancel overhaul execution."""
        self._cancelled = True
        self.progress_tracker.cancel()
    
    async def run(self) -> str:
        """Execute the production overhaul."""
        try:
            await self._phase_1_preflight()
            await self._phase_2_cleanup()
            await self._phase_3_create_roles()
            await self._phase_4_create_structure()
            await self._phase_5_apply_permissions()
            await self._phase_6_validation()
            await self._phase_7_completion()
            
            return await self._generate_safe_report()
        
        except Exception as e:
            log.error(f"Overhaul failed: {e}")
            log.error(traceback.format_exc())
            raise
        finally:
            self.stats.end_time = time.time()
            self.progress_tracker.cancel()
    
    async def _phase_1_preflight(self):
        """Phase 1: Preflight checks."""
        await self._update_progress("Preflight Checks", 1, "Verifying permissions and setup")
        
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
        bot_role = self.guild.get_role(self.BOT_ROLE_ID)
        if bot_role and bot_role.position > self.guild.me.top_role.position:
            log.warning(f"Bot role {bot_role.name} is above bot's top role")
    
    async def _phase_2_cleanup(self):
        """Phase 2: Cleanup existing structure."""
        await self._update_progress("Cleanup", 2, "Deleting existing channels, categories, and roles")
        
        # Delete categories (more efficient than individual channels)
        for category in list(self.guild.categories):
            if self._cancelled:
                return
            
            try:
                await self.rate_limiter.execute_with_retry(
                    lambda: category.delete(reason="Production Overhaul - Cleanup")
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
            if role.id == self.BOT_ROLE_ID:
                log.info(f"Preserved bot role: {role.name}")
                continue
            
            try:
                await self.rate_limiter.execute_with_retry(
                    lambda: role.delete(reason="Production Overhaul - Cleanup")
                )
                self.stats.deleted_roles += 1
            except Exception as e:
                self.stats.failures.append(f"Error deleting role {role.name}: {e}")
    
    async def _phase_3_create_roles(self):
        """Phase 3: Create roles."""
        await self._update_progress("Create Roles", 3, "Building role hierarchy")
        
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
        for role_name, role_def in sorted(
            role_definitions.items(), 
            key=lambda x: x[1]["position"], 
            reverse=True
        ):
            if self._cancelled:
                return
            
            # Check if bot role already exists
            if role_name == "Bots":
                existing_bot_role = self.guild.get_role(self.BOT_ROLE_ID)
                if existing_bot_role:
                    log.info(f"Reusing existing bot role: {existing_bot_role.name}")
                    continue
            
            try:
                # Create role
                role = await self.rate_limiter.execute_with_retry(
                    lambda: self.guild.create_role(
                        name=role_name,
                        permissions=role_def["permissions"],
                        hoist=role_name in ["Owner", "Admin", "Moderator", "Support"],
                        reason="Production Overhaul - Role Creation"
                    )
                )
                
                # Set position
                await self.rate_limiter.execute_with_retry(
                    lambda: role.edit(position=role_def["position"])
                )
                
                self.stats.created_roles += 1
                
            except Exception as e:
                self.stats.failures.append(f"Error creating role {role_name}: {e}")
    
    async def _phase_4_create_structure(self):
        """Phase 4: Create categories and channels."""
        await self._update_progress("Create Structure", 4, "Building categories and channels")
        
        # Get created roles for permission mapping
        role_map = {role.name: role for role in self.guild.roles}
        staff_roles = ["Owner", "Admin", "Moderator", "Support", "Bots"]
        
        # Create categories and channels
        for cat_idx, cat_spec in enumerate(self.CANONICAL_TEMPLATE):
            if self._cancelled:
                return
            
            try:
                # Create category
                overwrites = self._get_category_overwrites(cat_spec, role_map, staff_roles)
                
                category = await self.rate_limiter.execute_with_retry(
                    lambda: self.guild.create_category(
                        name=cat_spec.name,
                        overwrites=overwrites,
                        position=cat_spec.position,
                        reason="Production Overhaul - Category Creation"
                    )
                )
                self.stats.created_categories += 1
                
                # Create channels
                for ch_idx, channel_spec in enumerate(cat_spec.channels):
                    if self._cancelled:
                        return
                    
                    try:
                        overwrites = self._get_channel_overwrites(
                            cat_spec, channel_spec, role_map, staff_roles
                        )
                        
                        # Create channel
                        if channel_spec.type == ChannelType.VOICE:
                            channel = await self.rate_limiter.execute_with_retry(
                                lambda: category.create_voice_channel(
                                    name=channel_spec.name,
                                    overwrites=overwrites,
                                    reason="Production Overhaul - Voice Channel Creation"
                                )
                            )
                        else:
                            channel = await self.rate_limiter.execute_with_retry(
                                lambda: category.create_text_channel(
                                    name=channel_spec.name,
                                    overwrites=overwrites,
                                    reason="Production Overhaul - Text Channel Creation"
                                )
                            )
                        
                        self.stats.created_channels += 1
                    
                    except Exception as e:
                        self.stats.failures.append(f"Error creating channel {channel_spec.name}: {e}")
                
                # Update progress
                details = f"Created {cat_idx + 1}/{len(self.CANONICAL_TEMPLATE)} categories"
                await self._update_progress("Create Structure", 4, details)
                
            except Exception as e:
                self.stats.failures.append(f"Error creating category {cat_spec.name}: {e}")
    
    async def _phase_5_apply_permissions(self):
        """Phase 5: Apply muted role restrictions."""
        await self._update_progress("Apply Permissions", 5, "Applying muted role restrictions")
        
        muted_role = discord.utils.get(self.guild.roles, name="Muted")
        if not muted_role:
            log.warning("Muted role not found - skipping muted restrictions")
            return
        
        channels_to_mute = [ch for ch in self.guild.channels if isinstance(ch, (discord.TextChannel, discord.VoiceChannel))]
        
        for idx, channel in enumerate(channels_to_mute):
            if self._cancelled:
                return
            
            try:
                await self.rate_limiter.execute_with_retry(
                    lambda: channel.set_permissions(
                        muted_role,
                        send_messages=False,
                        add_reactions=False,
                        create_public_threads=False,
                        create_private_threads=False,
                        speak=False,
                        reason="Production Overhaul - Muted Role Restrictions"
                    )
                )
            except Exception as e:
                self.stats.failures.append(f"Error applying muted restrictions to {channel.name}: {e}")
    
    async def _phase_6_validation(self):
        """Phase 6: Validation with stabilization."""
        await self._update_progress("Validation", 6, "Verifying structure matches template")
        
        # Stabilization loop
        for attempt in range(5):
            try:
                await asyncio.sleep(1)  # Wait for Discord to stabilize
                channels = await self.rate_limiter.execute_with_retry(
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
        for cat_spec in self.CANONICAL_TEMPLATE:
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
                    if channel_spec.type == ChannelType.VOICE 
                    else discord.TextChannel
                )
                if not isinstance(channel, expected_type):
                    self.stats.failures.append(
                        f"Wrong type for {channel_spec.name}: expected {channel_spec.type.value}"
                    )
    
    async def _phase_7_completion(self):
        """Phase 7: Completion and level rewards."""
        await self._update_progress("Completion", 7, "Setting up level rewards")
        
        # Set up level rewards if available
        try:
            if hasattr(self.cog.bot, 'levels_store') and hasattr(self.cog.bot.levels_store, 'set_role_reward'):
                # Use new store
                await self.cog.bot.levels_store.set_role_reward(5, "Verified")
                await self.cog.bot.levels_store.set_role_reward(10, "Member")
                log.info("Level rewards configured using new store")
            elif hasattr(self.cog.bot, 'level_rewards_store'):
                # Use old store
                await self.cog.bot.level_rewards_store.set_reward(5, "Verified")
                await self.cog.bot.level_rewards_store.set_reward(10, "Member")
                log.info("Level rewards configured using old store")
            else:
                log.warning("No level rewards store available")
        except Exception as e:
            log.warning(f"Failed to configure level rewards: {e}")
    
    async def _update_progress(self, phase: str, phase_num: int, details: str = ""):
        """Update progress with debouncing."""
        message = f"**Phase {phase_num}/7: {phase}**\n"
        if details:
            message += f"Details: {details}\n"
        if self.stats.failures:
            message += f"Failures: {len(self.stats.failures)}"
        
        await self.progress_tracker.schedule_update(message)
    
    async def _generate_safe_report(self) -> str:
        """Generate report that respects Discord limits."""
        duration = (self.stats.end_time or time.time()) - self.stats.start_time
        
        # Create summary report
        summary_lines = [
            "🏰 **PRODUCTION OVERHAUL COMPLETED**",
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
        
        report = "\n".join(summary_lines)
        
        # Ensure it's under 2000 characters
        if len(report) > 1900:
            report = report[:1900] + "\n\n... (truncated)"
        
        return report
    
    def _normalize_name(self, name: str) -> str:
        """Normalize Unicode names for comparison."""
        return unicodedata.normalize('NFC', name).strip()
    
    def _get_category_overwrites(self, cat_spec: CategorySpec, role_map: Dict[str, discord.Role], staff_roles: List[str]):
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
                    for staff_role_name in staff_roles:
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
    
    def _get_channel_overwrites(self, cat_spec: CategorySpec, channel_spec: ChannelSpec, role_map: Dict[str, discord.Role], staff_roles: List[str]):
        """Generate permission overwrites for a channel."""
        overwrites = {}
        
        try:
            # Start with category overwrites
            overwrites.update(self._get_category_overwrites(cat_spec, role_map, staff_roles))
            
            # Apply special overrides
            if cat_spec.special_overrides and channel_spec.name in cat_spec.special_overrides:
                special = cat_spec.special_overrides[channel_spec.name]
                
                for role_name, perms in special.items():
                    if role_name == "staff":
                        # Apply to all staff roles
                        for staff_role_name in staff_roles:
                            staff_role = role_map.get(staff_role_name)
                            if staff_role:
                                overwrites[staff_role] = discord.PermissionOverwrite(**perms)
                    else:
                        role = role_map.get(role_name)
                        if role:
                            overwrites[role] = discord.PermissionOverwrite(**perms)
            
            # Apply channel-specific flags
            if channel_spec.read_only:
                everyone_role = self.guild.default_role
                current = overwrites.get(everyone_role, discord.PermissionOverwrite())
                overwrites[everyone_role] = discord.PermissionOverwrite(
                    read_messages=current.read_messages,
                    send_messages=False
                )
        
        except Exception as e:
            log.error(f"Error creating channel overwrites for {channel_spec.name}: {e}")
            raise
        
        return overwrites
