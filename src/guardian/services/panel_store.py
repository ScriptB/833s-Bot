from __future__ import annotations

import aiosqlite
import datetime
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class PanelRecord:
    """Represents a persistent UI panel record."""
    panel_key: str
    guild_id: int
    channel_id: int
    message_id: int
    updated_at: str
    schema_version: int = 1


class PanelStore:
    """SQLite storage for persistent UI panels."""
    
    def __init__(self, db_path: str):
        self._path = db_path
    
    async def initialize(self) -> None:
        """Initialize the database and create tables."""
        async with aiosqlite.connect(self._path) as db:
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
            await db.commit()
    
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
            cursor = await db.execute("""
                SELECT panel_key, guild_id, channel_id, message_id, updated_at, schema_version
                FROM panels
                WHERE panel_key = ? AND guild_id = ?
            """, (panel_key, guild_id))
            row = await cursor.fetchone()
            if row:
                return PanelRecord(*row)
            return None
    
    async def list_panels(self, guild_id: Optional[int] = None) -> List[PanelRecord]:
        """List all panels, optionally filtered by guild."""
        async with aiosqlite.connect(self._path) as db:
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
            return [PanelRecord(*row) for row in rows]
    
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
