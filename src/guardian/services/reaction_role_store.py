from __future__ import annotations

import aiosqlite
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
import logging
import json

from guardian.services.base import BaseService

log = logging.getLogger("guardian.reaction_role_store")


@dataclass
class ReactionRolePanel:
    """Represents a reaction role panel."""
    panel_id: str
    guild_id: int
    channel_id: int
    message_id: int
    title: str
    description: str
    mode: str  # toggle, add_only, remove_only, exclusive
    log_channel_id: Optional[int]
    created_by: int
    created_at: datetime
    options: List[Dict[str, Any]]  # List of {role_id, emoji, role_name}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "panel_id": self.panel_id,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "title": self.title,
            "description": self.description,
            "mode": self.mode,
            "log_channel_id": self.log_channel_id,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "options": json.dumps(self.options)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ReactionRolePanel:
        """Create from dictionary."""
        return cls(
            panel_id=data["panel_id"],
            guild_id=data["guild_id"],
            channel_id=data["channel_id"],
            message_id=data["message_id"],
            title=data["title"],
            description=data["description"],
            mode=data["mode"],
            log_channel_id=data.get("log_channel_id"),
            created_by=data["created_by"],
            created_at=datetime.fromisoformat(data["created_at"]),
            options=json.loads(data["options"]) if isinstance(data["options"], str) else data["options"]
        )
    
    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> ReactionRolePanel:
        """Create from database row."""
        return cls(
            panel_id=row["panel_id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            title=row["title"],
            description=row["description"],
            mode=row["mode"],
            log_channel_id=row["log_channel_id"],
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            options=json.loads(row["options"]) if isinstance(row["options"], str) else row["options"]
        )


class ReactionRoleStore(BaseService[ReactionRolePanel]):
    """Store for reaction role panels."""
    
    def __init__(self, sqlite_path: str, cache_ttl_seconds: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl_seconds)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        """Create reaction role panels table."""
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS reaction_role_panels (
                panel_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                mode TEXT NOT NULL,
                log_channel_id INTEGER NULL,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                options TEXT NOT NULL
            )
            """
        )
        
        # Create indexes for performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_rr_guild_id ON reaction_role_panels(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_rr_message_id ON reaction_role_panels(message_id)")
    
    def _from_row(self, row: aiosqlite.Row) -> ReactionRolePanel:
        """Create ReactionRolePanel from database row."""
        return ReactionRolePanel.from_row(row)
    
    @property
    def _get_query(self) -> str:
        return "SELECT * FROM reaction_role_panels WHERE panel_id = ?"
    
    async def get_all_panels(self) -> List[ReactionRolePanel]:
        """Get all panels."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT * FROM reaction_role_panels ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._from_row(row) for row in rows]
    
    async def get_by_guild(self, guild_id: int) -> List[ReactionRolePanel]:
        """Get all panels for a guild."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT * FROM reaction_role_panels WHERE guild_id = ? ORDER BY created_at DESC",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._from_row(row) for row in rows]
    
    async def get_by_message(self, message_id: int) -> Optional[ReactionRolePanel]:
        """Get panel by message ID."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT * FROM reaction_role_panels WHERE message_id = ?",
                (message_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return self._from_row(row) if row else None
    
    async def create(self, panel: ReactionRolePanel) -> ReactionRolePanel:
        """Create a new panel."""
        async with aiosqlite.connect(self._path) as db:
            data = panel.to_dict()
            await db.execute(
                """
                INSERT INTO reaction_role_panels 
                (panel_id, guild_id, channel_id, message_id, title, description, mode, 
                 log_channel_id, created_by, created_at, options)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["panel_id"], data["guild_id"], data["channel_id"], data["message_id"],
                    data["title"], data["description"], data["mode"], data["log_channel_id"],
                    data["created_by"], data["created_at"], data["options"]
                )
            )
            await db.commit()
            
            # Clear cache for this guild
            await self._clear_cache(f"guild_{panel.guild_id}")
            
            log.info(f"Created reaction role panel: {panel.panel_id}")
            return panel
    
    async def update(self, panel: ReactionRolePanel) -> ReactionRolePanel:
        """Update an existing panel."""
        async with aiosqlite.connect(self._path) as db:
            data = panel.to_dict()
            await db.execute(
                """
                UPDATE reaction_role_panels 
                SET channel_id = ?, message_id = ?, title = ?, description = ?, mode = ?,
                    log_channel_id = ?, options = ?
                WHERE panel_id = ?
                """,
                (
                    data["channel_id"], data["message_id"], data["title"], 
                    data["description"], data["mode"], data["log_channel_id"],
                    data["options"], data["panel_id"]
                )
            )
            await db.commit()
            
            # Clear cache
            await self._clear_cache(f"guild_{panel.guild_id}")
            await self._clear_cache(panel.panel_id)
            
            log.info(f"Updated reaction role panel: {panel.panel_id}")
            return panel
    
    async def delete(self, panel_id: str) -> bool:
        """Delete a panel."""
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                "DELETE FROM reaction_role_panels WHERE panel_id = ?",
                (panel_id,)
            )
            await db.commit()
            
            # Clear cache
            await self._clear_cache(panel_id)
            
            deleted = cursor.rowcount > 0
            if deleted:
                log.info(f"Deleted reaction role panel: {panel_id}")
            return deleted
    
    async def get_all_panels(self) -> List[ReactionRolePanel]:
        """Get all panels for startup loading."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT * FROM reaction_role_panels") as cursor:
                rows = await cursor.fetchall()
                return [self._from_row(row) for row in rows]
