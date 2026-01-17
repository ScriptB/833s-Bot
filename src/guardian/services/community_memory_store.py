from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import aiosqlite

from .base import BaseService


@dataclass(frozen=True)
class MemoryEntry:
    entry_id: int
    guild_id: int
    kind: str
    ts: int
    data: dict[str, Any]


class CommunityMemoryStore(BaseService):
    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS community_memory (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                ts INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                data_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
    
    def _from_row(self, row: aiosqlite.Row) -> MemoryEntry:
        try:
            data = json.loads(row["data_json"] or "{}")
        except Exception:
            data = {}
        return MemoryEntry(
            row["entry_id"],
            row["guild_id"],
            row["kind"],
            row["ts"],
            data,
        )
    
    @property
    def _get_query(self) -> str:
        return "SELECT * FROM community_memory WHERE entry_id = ?"

    async def add(self, guild_id: int, kind: str, data: dict[str, Any]) -> int:
        kind = (kind or "").strip()[:32]
        if not kind:
            raise ValueError("empty kind")
        payload = json.dumps(data or {}, ensure_ascii=False)[:4000]
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "INSERT INTO community_memory (guild_id, kind, data_json) VALUES (?, ?, ?)",
                (int(guild_id), kind, payload),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def latest(self, guild_id: int, limit: int = 10) -> Sequence[MemoryEntry]:
        limit = max(1, min(int(limit), 25))
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT entry_id, guild_id, kind, ts, data_json FROM community_memory WHERE guild_id=? ORDER BY entry_id DESC LIMIT ?",
                (int(guild_id), int(limit)),
            )
            rows = await cur.fetchall()
            out: list[MemoryEntry] = []
            for r in rows:
                try:
                    data = json.loads(r[4] or "{}")
                except Exception:
                    data = {}
                out.append(MemoryEntry(int(r[0]), int(r[1]), str(r[2]), int(r[3]), data))
            return out

    async def on_this_day(self, guild_id: int, month: int, day: int, limit: int = 10) -> Sequence[MemoryEntry]:
        limit = max(1, min(int(limit), 25))
        # SQLite strftime month/day from unix epoch in seconds.
        mm = f"{int(month):02d}"
        dd = f"{int(day):02d}"
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                """
                SELECT entry_id, guild_id, kind, ts, data_json
                FROM community_memory
                WHERE guild_id=?
                  AND strftime('%m', ts, 'unixepoch')=?
                  AND strftime('%d', ts, 'unixepoch')=?
                ORDER BY entry_id DESC
                LIMIT ?
                """
                ,
                (int(guild_id), mm, dd, int(limit)),
            )
            rows = await cur.fetchall()
            out: list[MemoryEntry] = []
            for r in rows:
                try:
                    data = json.loads(r[4] or "{}")
                except Exception:
                    data = {}
                out.append(MemoryEntry(int(r[0]), int(r[1]), str(r[2]), int(r[3]), data))
            return out
