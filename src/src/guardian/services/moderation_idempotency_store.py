from __future__ import annotations

import aiosqlite

from .base import BaseService


class ModerationIdempotencyStore(BaseService):
    """Dedupe keys for moderation actions.

    We store a (guild_id, dedupe_key) pair. If already present, the action is skipped.
    """

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS moderation_idempotency (
              guild_id INTEGER NOT NULL,
              dedupe_key TEXT NOT NULL,
              created_at_iso TEXT NOT NULL,
              PRIMARY KEY (guild_id, dedupe_key)
            )
            """
        )

    def _from_row(self, row: aiosqlite.Row):
        return row

    @property
    def _get_query(self) -> str:
        return "SELECT guild_id, dedupe_key, created_at_iso FROM moderation_idempotency WHERE guild_id = ? AND dedupe_key = ?"

    async def claim(self, guild_id: int, dedupe_key: str, created_at_iso: str) -> bool:
        """Try to claim a dedupe key. Returns True if newly claimed, False if already existed."""
        async with aiosqlite.connect(self._path) as db:
            try:
                await db.execute(
                    "INSERT INTO moderation_idempotency (guild_id, dedupe_key, created_at_iso) VALUES (?, ?, ?)",
                    (guild_id, dedupe_key, created_at_iso),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False
