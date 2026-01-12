from __future__ import annotations

import aiosqlite
from dataclasses import dataclass
from typing import Optional, List

from .base import BaseService


@dataclass
class RoleConfig:
    """Represents a configurable role for selection panels."""
    guild_id: int
    role_id: int
    label: str
    emoji: Optional[str]
    group: Optional[str]
    enabled: bool = True


class RoleConfigStore(BaseService[RoleConfig]):
    """SQLite storage for role selection configuration."""
    
    def __init__(self, db_path: str):
        super().__init__(db_path, cache_ttl_seconds=600)  # 10 minutes cache
    
    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        """Create the role_configs table."""
        await db.execute("""
            CREATE TABLE IF NOT EXISTS role_configs (
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                emoji TEXT,
                "group" TEXT,
                enabled BOOLEAN NOT NULL DEFAULT 1,
                PRIMARY KEY (guild_id, role_id)
            )
        """)
    
    def _from_row(self, row: aiosqlite.Row) -> RoleConfig:
        """Convert a database row to RoleConfig."""
        return RoleConfig(
            guild_id=row["guild_id"],
            role_id=row["role_id"],
            label=row["label"],
            emoji=row["emoji"],
            group=row["group"],
            enabled=bool(row["enabled"])
        )
    
    @property
    def _get_query(self) -> str:
        """SQL query for getting a role config by composite key."""
        # This is a placeholder - we'll use custom queries
        return "SELECT * FROM role_configs WHERE guild_id = ? AND role_id = ?"
    
    async def upsert_role(
        self, 
        guild_id: int, 
        role_id: int, 
        label: str, 
        emoji: Optional[str] = None,
        group: Optional[str] = None,
        enabled: bool = True
    ) -> None:
        """Insert or update a role configuration."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO role_configs 
                (guild_id, role_id, label, emoji, "group", enabled)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (guild_id, role_id, label, emoji, group, int(enabled)))
            await db.commit()
    
    async def get_role(self, guild_id: int, role_id: int) -> Optional[RoleConfig]:
        """Get a specific role configuration."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT guild_id, role_id, label, emoji, "group", enabled
                FROM role_configs
                WHERE guild_id = ? AND role_id = ?
            """, (guild_id, role_id))
            row = await cursor.fetchone()
            if row:
                return self._from_row(row)
            return None
    
    async def list_roles(self, guild_id: int, group: Optional[str] = None) -> List[RoleConfig]:
        """List all configured roles for a guild, optionally filtered by group."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            if group:
                cursor = await db.execute("""
                    SELECT guild_id, role_id, label, emoji, "group", enabled
                    FROM role_configs
                    WHERE guild_id = ? AND "group" = ? AND enabled = 1
                    ORDER BY "group", label
                """, (guild_id, group))
            else:
                cursor = await db.execute("""
                    SELECT guild_id, role_id, label, emoji, "group", enabled
                    FROM role_configs
                    WHERE guild_id = ? AND enabled = 1
                    ORDER BY "group", label
                """, (guild_id,))
            rows = await cursor.fetchall()
            return [self._from_row(row) for row in rows]
    
    async def delete_role(self, guild_id: int, role_id: int) -> None:
        """Delete a role configuration."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                DELETE FROM role_configs
                WHERE guild_id = ? AND role_id = ?
            """, (guild_id, role_id))
            await db.commit()
    
    async def get_groups(self, guild_id: int) -> List[str]:
        """Get all role groups for a guild."""
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute("""
                SELECT DISTINCT "group"
                FROM role_configs
                WHERE guild_id = ? AND "group" IS NOT NULL AND enabled = 1
                ORDER BY "group"
            """, (guild_id,))
            rows = await cursor.fetchall()
            return [row[0] for row in rows if row[0]]
