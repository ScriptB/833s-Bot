from __future__ import annotations

import aiosqlite
import logging
from typing import List, Dict, Any

from .base import BaseService

log = logging.getLogger("guardian.reaction_roles_store")

class ReactionRolesStore(BaseService):
    """Reaction roles configuration store following Discord.py best practices."""
    
    def __init__(self, sqlite_path: str, cache_ttl_seconds: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl_seconds)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        """Create reaction roles configuration table."""
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS reaction_roles_config (
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                group_key TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (guild_id, role_id)
            )
        """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_rrc_guild_id ON reaction_roles_config(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_rrc_group ON reaction_roles_config(guild_id, group_key)")

    async def init(self):
        """Initialize database schema."""
        async with aiosqlite.connect(self._path) as db:
            await self._create_tables(db)
            await db.commit()
        log.info("ReactionRolesStore initialized")

    async def add_roles(self, guild_id: int, role_ids: List[int], group_key: str) -> Dict[str, Any]:
        """Add multiple roles to a group with detailed feedback."""
        results = {"added": [], "skipped": [], "errors": []}
        
        async with aiosqlite.connect(self._path) as db:
            for role_id in role_ids:
                try:
                    await db.execute(
                        "INSERT OR REPLACE INTO reaction_roles_config (guild_id, role_id, group_key, enabled) VALUES (?, ?, ?, 1)",
                        (guild_id, role_id, group_key)
                    )
                    results["added"].append(role_id)
                except Exception as e:
                    results["errors"].append(f"Role {role_id}: {str(e)}")
            
            await db.commit()
        
        return results

    async def remove_roles(self, guild_id: int, role_ids: List[int]) -> Dict[str, Any]:
        """Remove multiple roles with detailed feedback."""
        results = {"removed": [], "errors": []}
        
        async with aiosqlite.connect(self._path) as db:
            for role_id in role_ids:
                try:
                    cursor = await db.execute(
                        "DELETE FROM reaction_roles_config WHERE guild_id = ? AND role_id = ?",
                        (guild_id, role_id)
                    )
                    if cursor.rowcount > 0:
                        results["removed"].append(role_id)
                    else:
                        results["errors"].append(f"Role {role_id}: Not found in configuration")
                except Exception as e:
                    results["errors"].append(f"Role {role_id}: {str(e)}")
            
            await db.commit()
        
        return results

    async def get_roles_by_group(self, guild_id: int, group_key: str) -> List[int]:
        """Get all role IDs in a specific group."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT role_id FROM reaction_roles_config WHERE guild_id = ? AND group_key = ? AND enabled = 1 ORDER BY role_id",
                (guild_id, group_key)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    async def get_all_roles(self, guild_id: int) -> Dict[str, List[int]]:
        """Get all roles grouped by group."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT group_key, role_id FROM reaction_roles_config WHERE guild_id = ? AND enabled = 1 ORDER BY group_key, role_id",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                
                groups = {}
                for group_key, role_id in rows:
                    if group_key not in groups:
                        groups[group_key] = []
                    groups[group_key].append(role_id)
                
                return groups

    async def get_configured_count(self, guild_id: int) -> int:
        """Get total configured roles count."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM reaction_roles_config WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
