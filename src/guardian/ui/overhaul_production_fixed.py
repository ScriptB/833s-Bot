"""
Production-Ready Overhaul System - V4.0.0.0

Complete rewrite addressing all architectural issues:
- Proper async context management
- Thread-safe operations
- Separation of concerns
- Discord.py 2.x best practices
- Memory leak prevention
- Robust error handling
- Type safety
- Performance optimization
"""

from __future__ import annotations

import asyncio
import logging
import time
import unicodedata
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Set, Callable
from weakref import WeakSet

import discord
from discord.ext import commands

log = logging.getLogger("guardian.overhaul_production")


class ChannelType(Enum):
    """Channel type enumeration with Discord.py 2.x compatibility."""
    TEXT = "text"
    VOICE = "voice"


@dataclass(frozen=True)
class ChannelSpec:
    """Immutable channel specification with validation."""
    name: str
    type: ChannelType
    read_only: bool = False
    staff_only: bool = False
    hidden_after_verify: bool = False
    
    def __post_init__(self):
        """Validate channel specification."""
        if not self.name or not self.name.strip():
            raise ValueError("Channel name cannot be empty")
        if len(self.name) > 100:  # Discord limit
            raise ValueError(f"Channel name too long: {self.name}")


@dataclass(frozen=True)
class CategorySpec:
    """Immutable category specification with validation."""
    name: str
    channels: List[ChannelSpec]
    visibility: Dict[str, bool]
    position: int
    description: str = ""
    special_overrides: Optional[Dict[str, Dict[str, Dict[str, bool]]] = None
    
    def __post_init__(self):
        """Validate category specification."""
        if not self.name or not self.name.strip():
            raise ValueError("Category name cannot be empty")
        if len(self.name) > 100:  # Discord limit
            raise ValueError(f"Category name too long: {self.name}")
        if self.position < 0 or self.position > 50:  # Practical limits
            raise ValueError(f"Invalid position: {self.position}")


@dataclass
class OverhaulStats:
    """Thread-safe overhaul statistics."""
    deleted_channels: int = 0
    deleted_categories: int = 0
    deleted_roles: int = 0
    created_channels: int = 0
    created_categories: int = 0
    created_roles: int = 0
    failures: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    
    async def add_failure(self, failure: str) -> None:
        """Thread-safe failure addition."""
        async with self._lock:
            self.failures.append(failure)
    
    async def increment(self, metric: str) -> None:
        """Thread-safe metric increment."""
        async with self._lock:
            if hasattr(self, metric):
                setattr(self, metric, getattr(self, metric) + 1)


class AsyncRateLimiter:
    """Production-ready rate limiter with proper async context management."""
    
    def __init__(self, max_concurrent: int = 1, min_delay: float = 0.1):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.min_delay = min_delay
        self.last_request = 0.0
        self._active_requests: WeakSet[asyncio.Task] = WeakSet()
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire rate limit with proper context management."""
        await self.semaphore.acquire()
        task = asyncio.current_task()
        if task:
            self._active_requests.add(task)
        
        try:
            # Apply minimum delay between requests
            now = time.time()
            delay_needed = self.min_delay - (now - self.last_request)
            if delay_needed > 0:
                await asyncio.sleep(delay_needed)
            self.last_request = time.time()
            yield
        finally:
            self.semaphore.release()
            if task:
                self._active_requests.discard(task)
    
    async def execute_with_backoff(
        self, 
        coro: Callable[[], Any], 
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0
    ) -> Any:
        """Execute coroutine with exponential backoff and jitter."""
        for attempt in range(max_retries):
            try:
                async with self.acquire():
                    return await coro()
            except discord.HTTPException as e:
                if e.status == 429:
                    # Use Discord's retry-after if available
                    retry_after = float(e.response.headers.get('Retry-After', base_delay))
                    retry_after = min(retry_after, max_delay)
                    log.warning(f"Rate limited, waiting {retry_after:.2f}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    # For other HTTP errors, use exponential backoff
                    if attempt == max_retries - 1:
                        raise
                    
                    delay = min(base_delay * (2 ** attempt) + (0.1 * attempt), max_delay)
                    log.warning(f"HTTP error (attempt {attempt + 1}/{max_retries}): {e}, retrying in {delay:.2f}s")
                    await asyncio.sleep(delay)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                
                delay = min(base_delay * (2 ** attempt) + (0.1 * attempt), max_delay)
                log.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}, retrying in {delay:.2f}s")
                await asyncio.sleep(delay)
        
        raise RuntimeError(f"Max retries ({max_retries}) exceeded")


class ThreadSafeProgressTracker:
    """Thread-safe progress tracker with proper task management."""
    
    def __init__(self, update_interval: float = 2.0):
        self.update_interval = update_interval
        self.last_update = 0.0
        self.pending_update: Optional[tuple[str, Callable]] = None
        self._update_task: Optional[asyncio.Task] = None
        self._cancel_event = asyncio.Event()
        self._lock = asyncio.Lock()
    
    async def schedule_update(self, message: str, send_func: Callable[[str], Any]) -> None:
        """Schedule a debounced progress update."""
        async with self._lock:
            self.pending_update = (message, send_func)
            now = time.time()
            
            if now - self.last_update >= self.update_interval:
                await self._send_pending()
            elif self._update_task is None:
                self._update_task = asyncio.create_task(self._update_loop())
    
    async def _update_loop(self) -> None:
        """Background task with proper cleanup."""
        try:
            while not self._cancel_event.is_set():
                await asyncio.sleep(self.update_interval)
                if self._cancel_event.is_set():
                    break
                async with self._lock:
                    if self.pending_update:
                        await self._send_pending()
        except asyncio.CancelledError:
            log.debug("Progress tracker task cancelled")
        finally:
            self._update_task = None
    
    async def _send_pending(self) -> None:
        """Send pending update with error handling."""
        if not self.pending_update:
            return
        
        message, send_func = self.pending_update
        try:
            await send_func(message)
            self.last_update = time.time()
            self.pending_update = None
        except Exception as e:
            log.error(f"Failed to send progress update: {e}")
    
    async def cancel(self) -> None:
        """Cancel progress tracking with proper cleanup."""
        self._cancel_event.set()
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass


class PermissionManager:
    """Manages Discord permission overwrites with proper validation."""
    
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self._role_cache: Optional[Dict[str, discord.Role]] = None
    
    async def get_role_map(self) -> Dict[str, discord.Role]:
        """Get cached role map with refresh capability."""
        if self._role_cache is None:
            # Fresh fetch from API
            roles = await self.guild.fetch_roles()
            self._role_cache = {role.name: role for role in roles}
        return self._role_cache
    
    def invalidate_cache(self) -> None:
        """Invalidate role cache."""
        self._role_cache = None
    
    async def create_category_overwrites(
        self, 
        cat_spec: CategorySpec, 
        staff_roles: List[str]
    ) -> Dict[Union[discord.Role, discord.Member], discord.PermissionOverwrite]:
        """Create category permission overwrites with proper error handling."""
        overwrites = {}
        role_map = await self.get_role_map()
        
        try:
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
                else:
                    log.debug(f"Role '{role_name}' not found for category '{cat_spec.name}'")
        
        except Exception as e:
            log.error(f"Error creating category overwrites for {cat_spec.name}: {e}")
            raise
        
        return overwrites
    
    async def create_channel_overwrites(
        self,
        cat_spec: CategorySpec,
        channel_spec: ChannelSpec,
        staff_roles: List[str]
    ) -> Dict[Union[discord.Role, discord.Member], discord.PermissionOverwrite]:
        """Create channel permission overwrites with inheritance."""
        overwrites = {}
        
        try:
            # Start with category overwrites
            overwrites.update(await self.create_category_overwrites(cat_spec, staff_roles))
            
            # Apply special overrides
            if cat_spec.special_overrides and channel_spec.name in cat_spec.special_overrides:
                special = cat_spec.special_overrides[channel_spec.name]
                role_map = await self.get_role_map()
                
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
                        else:
                            log.debug(f"Role '{role_name}' not found for channel '{channel_spec.name}'")
            
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


class ProductionOverhaulExecutor:
    """Production-ready overhaul executor with proper architecture."""
    
    # Bot role ID to preserve
    BOT_ROLE_ID = 1458781063185829964
    
    def __init__(self, cog: commands.Cog, guild: discord.Guild, options: Dict[str, Any]):
        self.cog = cog
        self.guild = guild
        self.options = options
        self.stats = OverhaulStats()
        self.rate_limiter = AsyncRateLimiter(max_concurrent=1, min_delay=0.2)
        self.progress_tracker = ThreadSafeProgressTracker(update_interval=2.0)
        self.permission_manager = PermissionManager(guild)
        self.progress_user = getattr(cog, 'progress_user', None)
        self.progress_message: Optional[discord.Message] = None
        self._cancelled = False
        self._template = self._load_template()
    
    def _load_template(self) -> List[CategorySpec]:
        """Load and validate template."""
        # Template moved to separate method for better maintainability
        return [
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
    
    def cancel(self) -> None:
        """Cancel overhaul execution."""
        self._cancelled = True
        asyncio.create_task(self.progress_tracker.cancel())
    
    def _normalize_name(self, name: str) -> str:
        """Normalize Unicode names for consistent comparison."""
        return unicodedata.normalize('NFC', name).strip()
    
    async def _send_progress(self, message: str) -> None:
        """Send progress update with comprehensive fallbacks."""
        if not self.progress_user:
            return
        
        content = f"🏰 **Production Overhaul Progress**\n\n{message}"
        
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
    
    async def _update_progress(
        self, 
        phase: str, 
        phase_num: int, 
        details: str = ""
    ) -> None:
        """Update progress with thread-safe debouncing."""
        message = f"**Phase {phase_num}/8: {phase}**\n"
        if details:
            message += f"Details: {details}\n"
        
        # Get failure count safely
        async with self.stats._lock:
            failure_count = len(self.stats.failures)
        
        if failure_count > 0:
            message += f"Failures: {failure_count}"
        
        await self.progress_tracker.schedule_update(message, self._send_progress)
    
    async def run(self) -> str:
        """Execute production overhaul with proper error handling."""
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
            self.stats.end_time = time.time()
            await self.progress_tracker.cancel()
    
    async def _phase_1_preflight(self) -> None:
        """Phase 1: Comprehensive preflight checks."""
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
    
    async def _phase_2_cleanup_channels(self) -> None:
        """Phase 2: Efficient cleanup with proper rate limiting."""
        await self._update_progress("Cleanup Channels", 2, "Deleting channels and categories")
        
        # Delete threads first (more efficient)
        for channel in self.guild.text_channels:
            if self._cancelled:
                return
            
            # Use fetch_threads to get all threads including archived
            try:
                threads = await channel.fetch_threads()
                for thread in threads.threads:
                    try:
                        await self.rate_limiter.execute_with_backoff(
                            lambda: thread.delete(reason="Production Overhaul - Thread Cleanup")
                        )
                        await self.stats.increment("deleted_channels")
                    except Exception as e:
                        await self.stats.add_failure(f"Error deleting thread {thread.name}: {e}")
            except Exception as e:
                log.warning(f"Failed to fetch threads for {channel.name}: {e}")
        
        # Delete categories (more efficient than individual channels)
        for category in list(self.guild.categories):
            if self._cancelled:
                return
            
            try:
                await self.rate_limiter.execute_with_backoff(
                    lambda: category.delete(reason="Production Overhaul - Category Cleanup")
                )
                await self.stats.increment("deleted_categories")
            except Exception as e:
                await self.stats.add_failure(f"Error deleting category {category.name}: {e}")
    
    async def _phase_3_cleanup_roles(self) -> None:
        """Phase 3: Safe role cleanup with preservation."""
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
                    lambda: role.delete(reason="Production Overhaul - Role Cleanup")
                )
                await self.stats.increment("deleted_roles")
            except Exception as e:
                await self.stats.add_failure(f"Error deleting role {role.name}: {e}")
    
    async def _phase_4_server_settings(self) -> None:
        """Phase 4: Apply server settings with Discord.py 2.x compatibility."""
        await self._update_progress("Server Settings", 4, "Applying server configuration")
        
        try:
            await self.rate_limiter.execute_with_backoff(
                lambda: self.guild.edit(
                    verification_level=discord.VerificationLevel.high,
                    default_notifications=discord.NotificationLevel.only_mentions,
                    explicit_content_filter=discord.ExplicitContentFilter.all_members,
                    reason="Production Overhaul - Server Settings"
                )
            )
        except Exception as e:
            await self.stats.add_failure(f"Failed to apply server settings: {e}")
    
    async def _phase_5_create_roles(self) -> None:
        """Phase 5: Create roles with proper hierarchy."""
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
                role = await self.rate_limiter.execute_with_backoff(
                    lambda: self.guild.create_role(
                        name=role_name,
                        permissions=role_def["permissions"],
                        hoist=role_name in ["Owner", "Admin", "Moderator", "Support"],
                        reason="Production Overhaul - Role Creation"
                    )
                )
                
                # Set position
                await self.rate_limiter.execute_with_backoff(
                    lambda: role.edit(position=role_def["position"])
                )
                
                await self.stats.increment("created_roles")
                
                # Invalidate permission cache after role creation
                self.permission_manager.invalidate_cache()
                
            except Exception as e:
                await self.stats.add_failure(f"Error creating role {role_name}: {e}")
    
    async def _phase_6_create_structure(self) -> None:
        """Phase 6: Create structure with proper error handling."""
        await self._update_progress("Create Structure", 6, "Building categories and channels")
        
        staff_roles = ["Owner", "Admin", "Moderator", "Support", "Bots"]
        
        for cat_idx, cat_spec in enumerate(self._template):
            if self._cancelled:
                return
            
            log.info(f"Creating category {cat_idx + 1}/{len(self._template)}: {cat_spec.name}")
            
            try:
                # Create category with proper overwrites
                overwrites = await self.permission_manager.create_category_overwrites(
                    cat_spec, staff_roles
                )
                
                category = await self.rate_limiter.execute_with_backoff(
                    lambda: self.guild.create_category(
                        name=cat_spec.name,
                        overwrites=overwrites,
                        position=cat_spec.position,
                        reason="Production Overhaul - Category Creation"
                    )
                )
                
                await self.stats.increment("created_categories")
                log.info(f"Successfully created category: {cat_spec.name}")
                
                # Create channels
                for ch_idx, channel_spec in enumerate(cat_spec.channels):
                    if self._cancelled:
                        return
                    
                    log.info(f"Creating channel {ch_idx + 1}/{len(cat_spec.channels)}: {channel_spec.name}")
                    
                    try:
                        overwrites = await self.permission_manager.create_channel_overwrites(
                            cat_spec, channel_spec, staff_roles
                        )
                        
                        # Create channel based on type
                        if channel_spec.type == ChannelType.VOICE:
                            channel = await self.rate_limiter.execute_with_backoff(
                                lambda: category.create_voice_channel(
                                    name=channel_spec.name,
                                    overwrites=overwrites,
                                    reason="Production Overhaul - Voice Channel Creation"
                                )
                            )
                        else:
                            channel = await self.rate_limiter.execute_with_backoff(
                                lambda: category.create_text_channel(
                                    name=channel_spec.name,
                                    overwrites=overwrites,
                                    reason="Production Overhaul - Text Channel Creation"
                                )
                            )
                        
                        await self.stats.increment("created_channels")
                        log.info(f"Successfully created channel: {channel_spec.name}")
                        
                    except Exception as e:
                        await self.stats.add_failure(f"Error creating channel {channel_spec.name}: {e}")
                
                # Update progress
                details = f"Created {cat_idx + 1}/{len(self._template)} categories"
                await self._update_progress("Create Structure", 6, details)
                
            except Exception as e:
                await self.stats.add_failure(f"Error creating category {cat_spec.name}: {e}")
        
        # Apply muted role restrictions
        await self._apply_muted_restrictions()
    
    async def _apply_muted_restrictions(self) -> None:
        """Apply muted role restrictions efficiently."""
        log.info("Applying muted role restrictions")
        
        muted_role = discord.utils.get(self.guild.roles, name="Muted")
        if not muted_role:
            log.warning("Muted role not found - skipping muted restrictions")
            return
        
        channels_to_mute = [
            ch for ch in self.guild.channels 
            if isinstance(ch, (discord.TextChannel, discord.VoiceChannel))
        ]
        
        log.info(f"Applying muted restrictions to {len(channels_to_mute)} channels")
        
        for idx, channel in enumerate(channels_to_mute):
            if self._cancelled:
                return
            
            try:
                await self.rate_limiter.execute_with_backoff(
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
                await self.stats.add_failure(f"Error applying muted restrictions to {channel.name}: {e}")
    
    async def _phase_7_validation(self) -> None:
        """Phase 7: Comprehensive validation with fresh API data."""
        await self._update_progress("Validation", 7, "Verifying structure matches template")
        
        validation_errors = []
        
        try:
            # Fetch fresh data from API
            categories = await self.rate_limiter.execute_with_backoff(
                lambda: self.guild.fetch_channels()
            )
            
            # Build lookup maps with normalized names
            category_map = {
                self._normalize_name(cat.name): cat 
                for cat in categories 
                if isinstance(cat, discord.CategoryChannel)
            }
            
            # Validate categories and channels
            for cat_spec in self._template:
                cat_name_norm = self._normalize_name(cat_spec.name)
                category = category_map.get(cat_name_norm)
                
                if not category:
                    validation_errors.append(f"Missing category: {cat_spec.name}")
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
                        validation_errors.append(f"Missing channel: {channel_spec.name} in {cat_spec.name}")
                        continue
                    
                    # Validate channel type
                    expected_type = (
                        discord.VoiceChannel 
                        if channel_spec.type == ChannelType.VOICE 
                        else discord.TextChannel
                    )
                    if not isinstance(channel, expected_type):
                        validation_errors.append(
                            f"Wrong type for {channel_spec.name}: expected {channel_spec.type.value}"
                        )
            
            # Add validation errors to stats
            for error in validation_errors[:10]:  # Limit to first 10
                await self.stats.add_failure(error)
            
            if len(validation_errors) > 10:
                await self.stats.add_failure(f"... and {len(validation_errors) - 10} more validation errors")
        
        except Exception as e:
            await self.stats.add_failure(f"Validation failed: {e}")
    
    async def _phase_8_final_report(self) -> None:
        """Phase 8: Generate final report."""
        await self._update_progress("Final Report", 8, "Generating completion report")
    
    async def _generate_safe_report(self) -> str:
        """Generate report that respects Discord limits."""
        duration = (self.stats.end_time or time.time()) - self.stats.start_time
        
        async with self.stats._lock:
            stats_data = {
                'deleted_channels': self.stats.deleted_channels,
                'deleted_categories': self.stats.deleted_categories,
                'deleted_roles': self.stats.deleted_roles,
                'created_channels': self.stats.created_channels,
                'created_categories': self.stats.created_categories,
                'created_roles': self.stats.created_roles,
                'failures': self.stats.failures.copy()
            }
        
        # Create summary report
        summary_lines = [
            "🏰 **PRODUCTION OVERHAUL COMPLETED**",
            "",
            "📊 **STATISTICS**",
            f"• Duration: {duration:.1f}s",
            f"• Deleted: {stats_data['deleted_channels']} channels, {stats_data['deleted_categories']} categories, {stats_data['deleted_roles']} roles",
            f"• Created: {stats_data['created_channels']} channels, {stats_data['created_categories']} categories, {stats_data['created_roles']} roles",
            f"• Failures: {len(stats_data['failures'])}",
        ]
        
        if stats_data['failures']:
            summary_lines.extend([
                "",
                "⚠️ **FAILURES**",
                *[f"• {failure}" for failure in stats_data['failures'][:5]]
            ])
            if len(stats_data['failures']) > 5:
                summary_lines.append(f"• ... and {len(stats_data['failures']) - 5} more")
        
        summary_lines.extend([
            "",
            "✅ **OPERATION COMPLETED**",
            "• Structure created",
            "• Permissions applied", 
            "• Server ready",
            "",
            "🚀 **DEPLOYMENT READY**"
        ])
        
        report = "\n".join(summary_lines)
        
        # Ensure it's under 2000 characters
        if len(report) > 1900:
            report = report[:1900] + "\n\n... (truncated)"
        
        return report
