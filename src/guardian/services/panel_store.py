from __future__ import annotations

import aiosqlite
import datetime
from dataclasses import dataclass
from typing import Optional, List

from .base import BaseService


@dataclass
class PanelRecord:
    """Represents a persistent UI panel record."""
    panel_key: str
    guild_id: int
    channel_id: int
    message_id: int
    updated_at: str
    schema_version: int = 1


class PanelStore(BaseService[PanelRecord]):
    """SQLite storage for persistent UI panels."""
    
    def __init__(self, db_path: str):
        super().__init__(db_path, cache_ttl_seconds=300)  # 5 minutes cache
    
    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        """Create the panels table."""
        await db.execute("""
            CREATE TABLE IF NOT EXISTS panels (
                panel_key TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (panel_key, guild_id)
            )
        """)
    
    def _from_row(self, row: aiosqlite.Row) -> PanelRecord:
        """Convert a database row to PanelRecord."""
        return PanelRecord(
            panel_key=row["panel_key"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            updated_at=row["updated_at"],
            schema_version=row["schema_version"]
        )
    
    @property
    def _get_query(self) -> str:
        """SQL query for getting a panel by composite key."""
        # This is a placeholder - we'll use custom queries
        return "SELECT * FROM panels WHERE panel_key = ? AND guild_id = ?"
    
    async def upsert_panel(
        self, 
        panel_key: str, 
        guild_id: int, 
        channel_id: int, 
        message_id: int,
        schema_version: int = 1
    ) -> None:
        """Insert or update a panel record."""
        now = datetime.datetime.utcnow().isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO panels 
                (panel_key, guild_id, channel_id, message_id, updated_at, schema_version)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (panel_key, guild_id, channel_id, message_id, now, schema_version))
            await db.commit()
    
    async def get_panel(self, panel_key: str, guild_id: int) -> Optional[PanelRecord]:
        """Get a specific panel record."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT panel_key, guild_id, channel_id, message_id, updated_at, schema_version
                FROM panels
                WHERE panel_key = ? AND guild_id = ?
            """, (panel_key, guild_id))
            row = await cursor.fetchone()
            if row:
                return self._from_row(row)
            return None
    
    async def list_panels(self, guild_id: Optional[int] = None) -> List[PanelRecord]:
        """List all panels, optionally filtered by guild."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            if guild_id:
                cursor = await db.execute("""
                    SELECT panel_key, guild_id, channel_id, message_id, updated_at, schema_version
                    FROM panels
                    WHERE guild_id = ?
                    ORDER BY panel_key
                """, (guild_id,))
            else:
                cursor = await db.execute("""
                    SELECT panel_key, guild_id, channel_id, message_id, updated_at, schema_version
                    FROM panels
                    ORDER BY guild_id, panel_key
                """)
            rows = await cursor.fetchall()
            return [self._from_row(row) for row in rows]
    
    async def delete_panel(self, panel_key: str, guild_id: int) -> None:
        """Delete a specific panel record."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                DELETE FROM panels
                WHERE panel_key = ? AND guild_id = ?
            """, (panel_key, guild_id))
            await db.commit()
    
    async def delete_guild_panels(self, guild_id: int) -> None:
        """Delete all panels for a guild (useful for guild removal)."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                DELETE FROM panels
                WHERE guild_id = ?
            """, (guild_id,))
            await db.commit()
