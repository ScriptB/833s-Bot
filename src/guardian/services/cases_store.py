from __future__ import annotations

from dataclasses import dataclass

import aiosqlite

from .base import BaseService


@dataclass(frozen=True)
class Case:
    guild_id: int
    case_id: int
    user_id: int
    actor_id: int
    action: str
    reason: str | None
    created_at: int


class CasesStore(BaseService):
    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                guild_id INTEGER NOT NULL,
                case_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                actor_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, case_id)
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cases_guild_user ON cases (guild_id, user_id, created_at)")
    
    def _from_row(self, row: aiosqlite.Row) -> Case:
        return Case(
            row["guild_id"],
            row["case_id"],
            row["user_id"],
            row["actor_id"],
            row["action"],
            row["reason"],
            row["created_at"],
        )
    
    @property
    def _get_query(self) -> str:
        return "SELECT * FROM cases WHERE guild_id = ? AND case_id = ?"

    async def next_id(self, guild_id: int) -> int:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT COALESCE(MAX(case_id), 0) + 1 FROM cases WHERE guild_id=?",
                (int(guild_id),),
            ) as cur:
                row = await cur.fetchone()
        return int(row[0]) if row else 1

    async def add(self, guild_id: int, user_id: int, actor_id: int, action: str, reason: str | None, created_at: int) -> int:
        cid = await self.next_id(guild_id)
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO cases (guild_id, case_id, user_id, actor_id, action, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (int(guild_id), int(cid), int(user_id), int(actor_id), str(action), reason, int(created_at)),
            )
            await db.commit()
        return cid

    async def list_for_user(self, guild_id: int, user_id: int, limit: int = 10) -> list[Case]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT case_id, actor_id, action, reason, created_at FROM cases WHERE guild_id=? AND user_id=? ORDER BY created_at DESC LIMIT ?",
                (int(guild_id), int(user_id), int(limit)),
            ) as cur:
                rows = await cur.fetchall()
        return [Case(int(guild_id), int(r[0]), int(user_id), int(r[1]), str(r[2]), r[3], int(r[4])) for r in rows]
