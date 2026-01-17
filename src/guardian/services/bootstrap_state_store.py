from __future__ import annotations

import aiosqlite

from .base import BaseService


class BootstrapStateStore(BaseService):
    """Persistent per-guild flags for one-time startup actions.

    Purpose: prevent redeploy spam (eg. bootstrapped messages, one-time setup).
    """

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS bootstrap_state (
                guild_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (guild_id, key)
            )
            """
        )

    @property
    def _get_query(self) -> str:
        return "SELECT guild_id, key, done, updated_at FROM bootstrap_state WHERE guild_id=? AND key=?"

    def _from_row(self, row: aiosqlite.Row):
        # Not used directly; BaseService requires it.
        return row

    async def is_done(self, guild_id: int, key: str) -> bool:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT done FROM bootstrap_state WHERE guild_id=? AND key=?",
                (int(guild_id), str(key)),
            ) as cur:
                row = await cur.fetchone()
        return bool(row[0]) if row else False

    async def mark_done(self, guild_id: int, key: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO bootstrap_state (guild_id, key, done, updated_at)
                VALUES (?, ?, 1, strftime('%s','now'))
                ON CONFLICT(guild_id, key) DO UPDATE SET
                    done=1,
                    updated_at=strftime('%s','now')
                """,
                (int(guild_id), str(key)),
            )
            await db.commit()
