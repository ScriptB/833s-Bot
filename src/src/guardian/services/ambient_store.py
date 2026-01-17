from __future__ import annotations

import aiosqlite

from .base import BaseService


class AmbientStore(BaseService):
    """Persistence for ambient feature preferences.

    Only stores user opt-in for mentions/pings.
    Cooldowns/counters are enforced in-memory to avoid excessive writes.
    """

    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ambient_prefs (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                pings_opt_in INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
    
    def _from_row(self, row: aiosqlite.Row) -> None:
        # Ambient don't need a specific data class for now
        return None
    
    @property
    def _get_query(self) -> str:
        return "SELECT * FROM ambient_prefs WHERE guild_id = ? AND user_id = ?"

    async def set_pings_opt_in(self, guild_id: int, user_id: int, enabled: bool) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO ambient_prefs (guild_id, user_id, pings_opt_in)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    pings_opt_in=excluded.pings_opt_in
                """,
                (int(guild_id), int(user_id), 1 if enabled else 0),
            )
            await db.commit()

    async def get_pings_opt_in(self, guild_id: int, user_id: int) -> bool:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT pings_opt_in FROM ambient_prefs WHERE guild_id=? AND user_id=?",
                (int(guild_id), int(user_id)),
            ) as cur:
                row = await cur.fetchone()
        return bool(row[0]) if row else False
