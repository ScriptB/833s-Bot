from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import aiosqlite

from .base import BaseService

log = logging.getLogger("guardian.reaction_roles_store")

@dataclass
class ReactionRoleConfig:
    """Represents a configured reaction role."""
    role_id: int
    group_key: str
    enabled: bool = True
    order_index: int = 0
    label: str | None = None
    emoji: str | None = None

class ReactionRolesStore(BaseService[ReactionRoleConfig]):
    """Store for reaction roles configuration."""
    
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
                order_index INTEGER NOT NULL,
                label TEXT NULL,
                emoji TEXT NULL,
                PRIMARY KEY (guild_id, role_id)
            )
        """
        )
        
        # Create indexes for performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_rrc_guild_id ON reaction_roles_config(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_rrc_group ON reaction_roles_config(guild_id, group_key)")

    def _from_row(self, row: aiosqlite.Row) -> ReactionRoleConfig:
        """Create ReactionRoleConfig from database row."""
        return ReactionRoleConfig(
            role_id=row["role_id"],
            group_key=row["group_key"],
            enabled=bool(row["enabled"]),
            order_index=row["order_index"],
            label=row["label"],
            emoji=row["emoji"]
        )

    @property
    def _get_query(self) -> str:
        return "SELECT * FROM reaction_roles_config WHERE guild_id = ? AND role_id = ?"

    async def add_roles(self, guild_id: int, role_configs: list[dict[str, Any]]) -> list[str]:
        """Add multiple roles to configuration."""
        errors = []
        
        async with aiosqlite.connect(self._path) as db:
            # Get current max order_index for this guild
            cursor = await db.execute(
                "SELECT COALESCE(MAX(order_index), -1) as max_order FROM reaction_roles_config WHERE guild_id = ?",
                (guild_id,)
            )
            max_order = (await cursor.fetchone())["max_order"]
            
            for i, config in enumerate(role_configs):
                try:
                    await db.execute(
                        """
                        INSERT OR REPLACE INTO reaction_roles_config 
                        (guild_id, role_id, group_key, enabled, order_index, label, emoji)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            guild_id,
                            config["role_id"],
                            config.get("group_key", "games"),
                            config.get("enabled", True),
                            max_order + i + 1,
                            config.get("label"),
                            config.get("emoji")
                        )
                    )
                except Exception as e:
                    errors.append(f"Role {config.get('role_id', 'unknown')}: {e}")
            
            await db.commit()
        
        return errors

    async def remove_roles(self, guild_id: int, role_ids: list[int]) -> list[str]:
        """Remove roles from configuration."""
        errors = []
        
        async with aiosqlite.connect(self._path) as db:
            for role_id in role_ids:
                try:
                    await db.execute(
                        "DELETE FROM reaction_roles_config WHERE guild_id = ? AND role_id = ?",
                        (guild_id, role_id)
                    )
                except Exception as e:
                    errors.append(f"Role {role_id}: {e}")
            
            await db.commit()
        
        return errors

    async def set_enabled(self, guild_id: int, role_id: int, enabled: bool) -> bool:
        """Toggle role enabled status."""
        try:
            async with aiosqlite.connect(self._path) as db:
                await db.execute(
                    "UPDATE reaction_roles_config SET enabled = ? WHERE guild_id = ? AND role_id = ?",
                    (int(enabled), guild_id, role_id)
                )
                await db.commit()
                return True
        except Exception as e:
            log.error(f"Failed to set enabled status for role {role_id}: {e}")
            return False

    async def set_group(self, guild_id: int, role_id: int, group_key: str) -> bool:
        """Change role group."""
        try:
            async with aiosqlite.connect(self._path) as db:
                await db.execute(
                    "UPDATE reaction_roles_config SET group_key = ? WHERE guild_id = ? AND role_id = ?",
                    (group_key, guild_id, role_id)
                )
                await db.commit()
                return True
        except Exception as e:
            log.error(f"Failed to set group for role {role_id}: {e}")
            return False

    async def set_label(self, guild_id: int, role_id: int, label: str | None) -> bool:
        """Set role label."""
        try:
            async with aiosqlite.connect(self._path) as db:
                await db.execute(
                    "UPDATE reaction_roles_config SET label = ? WHERE guild_id = ? AND role_id = ?",
                    (label, guild_id, role_id)
                )
                await db.commit()
                return True
        except Exception as e:
            log.error(f"Failed to set label for role {role_id}: {e}")
            return False

    async def set_emoji(self, guild_id: int, role_id: int, emoji: str | None) -> bool:
        """Set role emoji."""
        try:
            async with aiosqlite.connect(self._path) as db:
                await db.execute(
                    "UPDATE reaction_roles_config SET emoji = ? WHERE guild_id = ? AND role_id = ?",
                    (emoji, guild_id, role_id)
                )
                await db.commit()
                return True
        except Exception as e:
            log.error(f"Failed to set emoji for role {role_id}: {e}")
            return False

    async def move_role(self, guild_id: int, role_id: int, direction: str) -> bool:
        """Move role up or down in order."""
        try:
            async with aiosqlite.connect(self._path) as db:
                # Get current role and adjacent role
                cursor = await db.execute(
                    """
                    SELECT role_id, order_index FROM reaction_roles_config 
                    WHERE guild_id = ? 
                    ORDER BY order_index
                    """,
                    (guild_id,)
                )
                roles = await cursor.fetchall()
                
                # Find current role index
                current_idx = next((i for i, r in enumerate(roles) if r["role_id"] == role_id), None)
                if current_idx is None:
                    return False
                
                # Calculate new position
                if direction == "up" and current_idx > 0:
                    new_idx = current_idx - 1
                elif direction == "down" and current_idx < len(roles) - 1:
                    new_idx = current_idx + 1
                else:
                    return False
                
                # Swap order indices
                current_role = roles[current_idx]
                target_role = roles[new_idx]
                
                await db.execute(
                    "UPDATE reaction_roles_config SET order_index = ? WHERE guild_id = ? AND role_id = ?",
                    (target_role["order_index"], guild_id, current_role["role_id"])
                )
                await db.execute(
                    "UPDATE reaction_roles_config SET order_index = ? WHERE guild_id = ? AND role_id = ?",
                    (current_role["order_index"], guild_id, target_role["role_id"])
                )
                await db.commit()
                return True
        except Exception as e:
            log.error(f"Failed to move role {role_id}: {e}")
            return False

    async def list_roles(self, guild_id: int) -> list[ReactionRoleConfig]:
        """List all configured roles for a guild."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                """
                SELECT * FROM reaction_roles_config 
                WHERE guild_id = ? 
                ORDER BY group_key, order_index
                """,
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._from_row(row) for row in rows]

    async def list_group(self, guild_id: int, group_key: str) -> list[ReactionRoleConfig]:
        """List roles in a specific group."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                """
                SELECT * FROM reaction_roles_config 
                WHERE guild_id = ? AND group_key = ? AND enabled = 1
                ORDER BY order_index
                """,
                (guild_id, group_key)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._from_row(row) for row in rows]

    async def get_groups(self, guild_id: int) -> list[str]:
        """Get all group keys for a guild."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT DISTINCT group_key FROM reaction_roles_config WHERE guild_id = ? ORDER BY group_key",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row["group_key"] for row in rows]
