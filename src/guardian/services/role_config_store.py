from __future__ import annotations

import aiosqlite
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class RoleConfig:
    """Represents a configurable role for selection panels."""
    guild_id: int
    role_id: int
    label: str
    emoji: Optional[str]
    group: Optional[str]
    enabled: bool = True


class RoleConfigStore:
    """SQLite storage for role selection configuration."""
    
    def __init__(self, db_path: str):
        self._path = db_path
    
    async def initialize(self) -> None:
        """Initialize the database and create tables."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS role_configs (
                    guild_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    emoji TEXT,
                    group TEXT,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    PRIMARY KEY (guild_id, role_id)
                )
            """)
            await db.commit()
    
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
                (guild_id, role_id, label, emoji, group, enabled)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (guild_id, role_id, label, emoji, group, int(enabled)))
            await db.commit()
    
    async def get_role(self, guild_id: int, role_id: int) -> Optional[RoleConfig]:
        """Get a specific role configuration."""
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute("""
                SELECT guild_id, role_id, label, emoji, group, enabled
                FROM role_configs
                WHERE guild_id = ? AND role_id = ?
            """, (guild_id, role_id))
            row = await cursor.fetchone()
            if row:
                return RoleConfig(
                    guild_id=row[0],
                    role_id=row[1], 
                    label=row[2],
                    emoji=row[3],
                    group=row[4],
                    enabled=bool(row[5])
                )
            return None
    
    async def list_roles(self, guild_id: int, group: Optional[str] = None) -> List[RoleConfig]:
        """List all configured roles for a guild, optionally filtered by group."""
        async with aiosqlite.connect(self._path) as db:
            if group:
                cursor = await db.execute("""
                    SELECT guild_id, role_id, label, emoji, group, enabled
                    FROM role_configs
                    WHERE guild_id = ? AND group = ? AND enabled = 1
                    ORDER BY group, label
                """, (guild_id, group))
            else:
                cursor = await db.execute("""
                    SELECT guild_id, role_id, label, emoji, group, enabled
                    FROM role_configs
                    WHERE guild_id = ? AND enabled = 1
                    ORDER BY group, label
                """, (guild_id,))
            rows = await cursor.fetchall()
            return [
                RoleConfig(
                    guild_id=row[0],
                    role_id=row[1],
                    label=row[2],
                    emoji=row[3],
                    group=row[4],
                    enabled=bool(row[5])
                )
                for row in rows
            ]
    
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
                SELECT DISTINCT group
                FROM role_configs
                WHERE guild_id = ? AND group IS NOT NULL AND enabled = 1
                ORDER BY group
            """, (guild_id,))
            rows = await cursor.fetchall()
            return [row[0] for row in rows if row[0]]
