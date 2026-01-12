from __future__ import annotations

import logging
import aiosqlite
from dataclasses import dataclass
from typing import Sequence

from .base import BaseService

log = logging.getLogger("guardian.events_store")


@dataclass(frozen=True)
class Event:
    event_id: int
    guild_id: int
    creator_id: int
    title: str
    description: str
    start_ts: int
    channel_id: int
    created_at: int
    active: bool


class EventsStore(BaseService):
    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                start_ts INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL DEFAULT strftime('%s','now'),
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS event_participants (
                event_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at INTEGER NOT NULL DEFAULT strftime('%s','now'),
                PRIMARY KEY (event_id, guild_id, user_id),
                FOREIGN KEY(event_id) REFERENCES events(event_id)
            )
            """
        )

    def _from_row(self, row: aiosqlite.Row) -> Event:
        return Event(
            row["event_id"],
            row["guild_id"],
            row["creator_id"],
            row["title"],
            row["description"],
            row["start_ts"],
            row["channel_id"],
            row["created_at"],
            bool(row["active"]),
        )

    @property
    def _get_query(self) -> str:
        return "SELECT * FROM events WHERE event_id = ?"

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await self._create_tables(db)
            await db.commit()

    async def active_count(self, guild_id: int) -> int:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute("SELECT COUNT(1) FROM events WHERE guild_id=? AND active=1", (int(guild_id),))
            row = await cur.fetchone()
            return int(row[0] or 0)

    async def create_event(
        self,
        guild_id: int,
        creator_id: int,
        *,
        title: str,
        description: str,
        start_ts: int,
        channel_id: int,
    ) -> int:
        title = (title or "").strip()[:80]
        description = (description or "").strip()[:700]
        if not title:
            raise ValueError("empty title")
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "INSERT INTO events (guild_id, creator_id, title, description, start_ts, channel_id) VALUES (?, ?, ?, ?, ?, ?)",
                (int(guild_id), int(creator_id), title, description, int(start_ts), int(channel_id)),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def get(self, guild_id: int, event_id: int) -> Event | None:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT event_id, guild_id, creator_id, title, description, start_ts, channel_id, created_at, active FROM events WHERE guild_id=? AND event_id=?",
                (int(guild_id), int(event_id)),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return Event(int(row[0]), int(row[1]), int(row[2]), str(row[3]), str(row[4]), int(row[5]), int(row[6]), int(row[7]), bool(int(row[8])))

    async def list_active(self, guild_id: int, limit: int = 10) -> Sequence[Event]:
        limit = max(1, min(int(limit), 25))
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT event_id, guild_id, creator_id, title, description, start_ts, channel_id, created_at, active FROM events WHERE guild_id=? AND active=1 ORDER BY start_ts ASC LIMIT ?",
                (int(guild_id), int(limit)),
            )
            rows = await cur.fetchall()
            return [Event(int(r[0]), int(r[1]), int(r[2]), str(r[3]), str(r[4]), int(r[5]), int(r[6]), int(r[7]), bool(int(r[8]))) for r in rows]

    async def set_active(self, guild_id: int, event_id: int, active: bool) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("UPDATE events SET active=? WHERE guild_id=? AND event_id=?", (1 if active else 0, int(guild_id), int(event_id)))
            await db.commit()

    async def join(self, guild_id: int, event_id: int, user_id: int) -> bool:
        async with aiosqlite.connect(self._path) as db:
            try:
                cur = await db.execute(
                    "INSERT OR IGNORE INTO event_participants (event_id, guild_id, user_id) VALUES (?, ?, ?)",
                    (int(event_id), int(guild_id), int(user_id)),
                )
                await db.commit()
                return (cur.rowcount or 0) > 0
            except aiosqlite.Error:
                log.exception("Failed to join event (guild_id=%s event_id=%s user_id=%s)", int(guild_id), int(event_id), int(user_id))
                return False

    async def leave(self, guild_id: int, event_id: int, user_id: int) -> bool:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "DELETE FROM event_participants WHERE event_id=? AND guild_id=? AND user_id=?",
                (int(event_id), int(guild_id), int(user_id)),
            )
            await db.commit()
            return (cur.rowcount or 0) > 0

    async def participants_count(self, guild_id: int, event_id: int) -> int:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT COUNT(1) FROM event_participants WHERE guild_id=? AND event_id=?",
                (int(guild_id), int(event_id)),
            )
            row = await cur.fetchone()
            return int(row[0] or 0)
