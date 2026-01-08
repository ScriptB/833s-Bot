from __future__ import annotations

import aiosqlite
from dataclasses import dataclass


@dataclass(frozen=True)
class TitleState:
    guild_id: int
    user_id: int
    equipped: str


class TitlesStore:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS titles (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    equipped TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            await db.commit()

    async def get(self, guild_id: int, user_id: int) -> TitleState:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT equipped FROM titles WHERE guild_id=? AND user_id=?",
                (int(guild_id), int(user_id)),
            )
            row = await cur.fetchone()
            if not row:
                return TitleState(int(guild_id), int(user_id), "")
            return TitleState(int(guild_id), int(user_id), str(row[0] or ""))

    async def set_equipped(self, guild_id: int, user_id: int, title: str) -> None:
        title = (title or "").strip()[:48]
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO titles (guild_id, user_id, equipped, updated_at)
                VALUES (?, ?, ?, strftime('%s','now'))
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    equipped=excluded.equipped,
                    updated_at=excluded.updated_at
                """
                ,
                (int(guild_id), int(user_id), title),
            )
            await db.commit()
