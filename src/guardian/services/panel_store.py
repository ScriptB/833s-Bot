from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import aiosqlite

from ..interfaces import DatabaseSafety, validate_panel_store
from .base import BaseService

log = logging.getLogger("guardian.panel_store")


class PanelRecord:
    """Represents a stored panel record."""
    
    def __init__(self, guild_id: int, panel_key: str, channel_id: int, message_id: int, 
                 schema_version: int = 1, last_deployed_at: datetime | None = None):
        self.guild_id = guild_id
        self.panel_key = panel_key
        self.channel_id = channel_id
        self.message_id = message_id
        self.schema_version = schema_version
        self.last_deployed_at = last_deployed_at or datetime.utcnow()
    
    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> PanelRecord:
        """Create PanelRecord from database row."""
        return cls(
            guild_id=row["guild_id"],
            panel_key=row["panel_key"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            schema_version=row["schema_version"],
            last_deployed_at=datetime.fromisoformat(row["last_deployed_at"]) if row["last_deployed_at"] else None
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        return {
            "guild_id": self.guild_id,
            "panel_key": self.panel_key,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "schema_version": self.schema_version,
            "last_deployed_at": self.last_deployed_at.isoformat() if self.last_deployed_at else None
        }


class PanelStore(BaseService[PanelRecord]):
    """SQLite storage for persistent UI panels."""
    
    def __init__(self, db_path: str):
        super().__init__(db_path, cache_ttl_seconds=300)  # 5 minutes cache
        
        # Validate interface compliance at runtime
        validate_panel_store(self)
    
    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        """Create panels table."""
        await db.execute("""
            CREATE TABLE IF NOT EXISTS panels (
                guild_id INTEGER NOT NULL,
                panel_key TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                last_deployed_at TEXT,
                PRIMARY KEY (guild_id, panel_key)
            )
        """)
    
    async def _execute(self, sql: str, params: tuple = ()) -> None:
        """Execute SQL with parameters and commit."""
        async def _db_op():
            async with aiosqlite.connect(self._path) as db:
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA foreign_keys=ON")
                await db.execute(sql, params)
                await db.commit()
        
        await DatabaseSafety.safe_execute_with_retry(_db_op)
    
    async def _fetchone(self, sql: str, params: tuple = ()) -> tuple | None:
        """Execute SQL and fetch one row."""
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(sql, params)
            return await cursor.fetchone()
    
    async def _fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        """Execute SQL and fetch all rows."""
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(sql, params)
            return await cursor.fetchall()
    
    async def init(self) -> None:
        """Initialize database schema."""
        await self._execute("""
            CREATE TABLE IF NOT EXISTS panels (
              guild_id INTEGER NOT NULL,
              panel_key TEXT NOT NULL,
              channel_id INTEGER NOT NULL,
              message_id INTEGER NOT NULL,
              schema_version INTEGER NOT NULL DEFAULT 1,
              last_deployed_at TEXT,
              PRIMARY KEY (guild_id, panel_key)
            )
        """)
    
    def _from_row(self, row: aiosqlite.Row) -> PanelRecord:
        """Convert database row to PanelRecord."""
        return PanelRecord.from_row(row)
    
    def _get_query(self) -> str:
        """Get query for fetching a single record."""
        return "SELECT * FROM panels WHERE guild_id = ? AND panel_key = ?"
    
    async def upsert(self, guild_id: int, panel_key: str, channel_id: int, 
                    message_id: int, schema_version: int = 1) -> None:
        """Insert or update a panel record."""
        await self._execute("""
            INSERT OR REPLACE INTO panels 
            (guild_id, panel_key, channel_id, message_id, schema_version, last_deployed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (guild_id, panel_key, channel_id, message_id, schema_version, datetime.utcnow().isoformat()))
        
        # Clear cache for this record
        cache_key = f"{guild_id}:{panel_key}"
        self._cache.delete(cache_key)
    
    async def get(self, guild_id: int, panel_key: str) -> dict | None:
        """Get panel record (interface compliance)."""
        cache_key = f"{guild_id}:{panel_key}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached.to_dict()
        
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(self._get_query(), (guild_id, panel_key))
            row = await cur.fetchone()
            await cur.close()
            
            if row is None:
                return None
            
            record = self._from_row(row)
            self._cache.set(cache_key, record)
            return record.to_dict()
    
    async def list_guild(self, guild_id: int) -> list[dict]:
        """List all panels for guild (interface compliance)."""
        panels = await self.list_guild_panels(guild_id)
        return [panel.to_dict() for panel in panels]
    
    async def list_guild_panels(self, guild_id: int) -> list[PanelRecord]:
        """List all panels for a guild."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM panels WHERE guild_id = ?", (guild_id,))
            rows = await cur.fetchall()
            await cur.close()
            return [self._from_row(row) for row in rows]
    
    async def list_all_panels(self) -> list[PanelRecord]:
        """List all panels across all guilds."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM panels")
            rows = await cur.fetchall()
            await cur.close()
            return [self._from_row(row) for row in rows]
    
    async def delete(self, guild_id: int, panel_key: str) -> None:
        """Delete a panel record."""
        await self._execute("DELETE FROM panels WHERE guild_id = ? AND panel_key = ?", (guild_id, panel_key))
        
        # Clear cache
        cache_key = f"{guild_id}:{panel_key}"
        self._cache.delete(cache_key)
