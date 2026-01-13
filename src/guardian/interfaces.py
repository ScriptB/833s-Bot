"""
Interface contracts for 833s Guardian bot fault tolerance.

This module defines stable interfaces that all components must follow
to prevent cascading failures and ensure consistency.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable, Optional, List, Tuple
import discord


@runtime_checkable
class ProgressReporter(Protocol):
    """Stable progress reporting interface."""
    
    @abstractmethod
    async def init(self) -> None:
        """Initialize progress reporter."""
        ...
    
    @abstractmethod
    async def update(self, phase: str, done: int, total: int, detail: str = "") -> None:
        """Update progress."""
        ...
    
    @abstractmethod
    async def finalize(self, ok: bool, summary: str) -> None:
        """Finalize with success/failure."""
        ...
    
    @abstractmethod
    async def fail(self, summary: str) -> None:
        """Mark as failed."""
        ...


@runtime_checkable
class PanelStore(Protocol):
    """Stable panel storage interface."""
    
    @abstractmethod
    async def init(self) -> None:
        """Initialize database schema."""
        ...
    
    @abstractmethod
    async def upsert(self, guild_id: int, panel_key: str, channel_id: int, 
                    message_id: int, schema_version: int = 1) -> None:
        """Insert or update panel record."""
        ...
    
    @abstractmethod
    async def get(self, guild_id: int, panel_key: str) -> Optional[dict]:
        """Get panel record."""
        ...
    
    @abstractmethod
    async def delete(self, guild_id: int, panel_key: str) -> None:
        """Delete panel record."""
        ...
    
    @abstractmethod
    async def list_guild(self, guild_id: int) -> List[dict]:
        """List all panels for guild."""
        ...


def validate_progress_reporter(reporter: object) -> ProgressReporter:
    """Validate and return ProgressReporter interface."""
    if not isinstance(reporter, ProgressReporter):
        raise AttributeError(f"Object {reporter} does not implement ProgressReporter interface")
    
    # Check required methods exist at runtime
    required_methods = ['init', 'update', 'finalize', 'fail']
    for method in required_methods:
        if not hasattr(reporter, method):
            raise AttributeError(f"ProgressReporter missing required method: {method}")
        if not getattr(reporter, method):
            raise AttributeError(f"ProgressReporter method {method} is not callable")
    
    return reporter


def validate_panel_store(store: object) -> PanelStore:
    """Validate and return PanelStore interface."""
    if not isinstance(store, PanelStore):
        raise AttributeError(f"Object {store} does not implement PanelStore interface")
    
    # Check required methods exist at runtime
    required_methods = ['init', 'upsert', 'get', 'delete', 'list_guild']
    for method in required_methods:
        if not hasattr(store, method):
            raise AttributeError(f"PanelStore missing required method: {method}")
        if not getattr(store, method):
            raise AttributeError(f"PanelStore method {method} is not callable")
    
    return store


def has_required_guild_perms(member: discord.Member) -> Tuple[bool, List[str]]:
    """Check if member has required guild permissions."""
    required_perms = [
        "manage_guild",
        "manage_channels", 
        "manage_roles",
        "administrator"
    ]
    
    # Administrator bypasses individual checks
    if getattr(member.guild_permissions, "administrator", False):
        return True, []
    
    missing = []
    for perm in required_perms:
        if not getattr(member.guild_permissions, perm, False):
            missing.append(perm)
    
    return len(missing) == 0, missing


def sanitize_user_text(text: str) -> str:
    """Remove internal bootstrap tags from user-facing text."""
    import re
    # Remove any leading tag like [833s-guardian:bootstrap:v1]
    return re.sub(r'^\[[^\]]+\]\s*', '', text).strip()


class OperationSnapshot:
    """Snapshot of guild state for destructive operations."""
    
    def __init__(self, guild: discord.Guild):
        self.guild_id = guild.id
        self.channels_count = len([c for c in guild.channels if not isinstance(c, discord.CategoryChannel)])
        self.categories_count = len(guild.categories)
        self.roles_count = len(guild.roles)
        self.timestamp = discord.utils.utcnow()
    
    def has_items(self) -> bool:
        """Check if there were items to delete."""
        return (self.channels_count > 0 or 
                self.categories_count > 0 or 
                self.roles_count > 0)
    
    def verify_deletion(self, deleted_channels: int, deleted_categories: int, 
                      deleted_roles: int) -> Tuple[bool, str]:
        """Verify deletion was successful."""
        if self.has_items() and deleted_channels == 0 and deleted_categories == 0 and deleted_roles == 0:
            return False, "Deletion failed - no items were deleted"
        return True, "Deletion verified"


class DatabaseSafety:
    """Database safety helpers."""
    
    @staticmethod
    async def safe_execute_with_retry(db_func, max_retries: int = 3, backoff: float = 1.0):
        """Execute database function with retry on locked errors."""
        import asyncio
        import aiosqlite
        
        for attempt in range(max_retries):
            try:
                return await db_func()
            except aiosqlite.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    await asyncio.sleep(backoff * (2 ** attempt))
                    continue
                raise
            except Exception:
                raise
