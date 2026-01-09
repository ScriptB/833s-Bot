from __future__ import annotations

import aiosqlite

from .base import BaseService


class ReactionRolesStore(BaseService):
    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS rr_panels (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                max_values INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (guild_id, message_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS rr_options (
                guild_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                emoji TEXT NULL,
                PRIMARY KEY (guild_id, message_id, role_id)
            )
            """
        )
    
    def _from_row(self, row: aiosqlite.Row) -> None:
        # Reaction roles don't need a specific data class for now
        return None
    
    @property
    def _get_query(self) -> str:
        return "SELECT * FROM rr_panels WHERE guild_id = ?"

    async def create_panel(self, guild_id: int, channel_id: int, message_id: int, title: str, description: str, max_values: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO rr_panels (guild_id, channel_id, message_id, title, description, max_values) VALUES (?, ?, ?, ?, ?, ?)",
                (int(guild_id), int(channel_id), int(message_id), title, description, int(max_values)),
            )
            await db.commit()

    async def add_option(self, guild_id: int, message_id: int, role_id: int, label: str, emoji: str | None) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO rr_options (guild_id, message_id, role_id, label, emoji) VALUES (?, ?, ?, ?, ?)",
                (int(guild_id), int(message_id), int(role_id), label, emoji),
            )
            await db.commit()

    async def remove_option(self, guild_id: int, message_id: int, role_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "DELETE FROM rr_options WHERE guild_id=? AND message_id=? AND role_id=?",
                (int(guild_id), int(message_id), int(role_id)),
            )
            await db.commit()

    async def get_panel(self, guild_id: int, message_id: int):
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT channel_id, title, description, max_values FROM rr_panels WHERE guild_id=? AND message_id=?",
                (int(guild_id), int(message_id)),
            ) as cur:
                panel = await cur.fetchone()
            if not panel:
                return None
            async with db.execute(
                "SELECT role_id, label, emoji FROM rr_options WHERE guild_id=? AND message_id=? ORDER BY label ASC",
                (int(guild_id), int(message_id)),
            ) as cur:
                options = await cur.fetchall()
        return panel, options

    async def list_panels(self, guild_id: int):
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT channel_id, message_id FROM rr_panels WHERE guild_id=? ORDER BY message_id DESC",
                (int(guild_id),),
            ) as cur:
                return await cur.fetchall()
