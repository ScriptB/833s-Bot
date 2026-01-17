from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import aiosqlite

from .base import BaseService


@dataclass(frozen=True)
class Profile:
    guild_id: int
    user_id: int
    about: str
    pronouns: str
    interests: list[str]
    is_public: bool


class ProfilesStore(BaseService):
    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                about TEXT NOT NULL DEFAULT '',
                pronouns TEXT NOT NULL DEFAULT '',
                interests TEXT NOT NULL DEFAULT '',
                is_public INTEGER NOT NULL DEFAULT 1,
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
    
    def _from_row(self, row: aiosqlite.Row) -> Profile:
        return Profile(
            row["guild_id"],
            row["user_id"],
            row["about"],
            row["pronouns"],
            self._split_interests(row["interests"]),
            bool(row["is_public"]),
        )
    
    @property
    def _get_query(self) -> str:
        return "SELECT * FROM profiles WHERE guild_id = ? AND user_id = ?"

    def _split_interests(self, raw: str) -> list[str]:
        raw = (raw or "").strip()
        if not raw:
            return []
        parts = [p.strip() for p in raw.split(",")]
        out: list[str] = []
        seen: set[str] = set()
        for p in parts:
            if not p:
                continue
            k = p.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(p[:32])
            if len(out) >= 12:
                break
        return out

    def _join_interests(self, interests: Iterable[str]) -> str:
        cleaned: list[str] = []
        seen: set[str] = set()
        for it in interests:
            it = (it or "").strip()
            if not it:
                continue
            k = it.lower()
            if k in seen:
                continue
            seen.add(k)
            cleaned.append(it[:32])
            if len(cleaned) >= 12:
                break
        return ", ".join(cleaned)

    async def get(self, guild_id: int, user_id: int) -> Profile:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT about, pronouns, interests, is_public FROM profiles WHERE guild_id=? AND user_id=?",
                (int(guild_id), int(user_id)),
            )
            row = await cur.fetchone()
            if not row:
                return Profile(int(guild_id), int(user_id), "", "", [], True)
            about, pronouns, interests, is_public = row
            return Profile(
                int(guild_id),
                int(user_id),
                str(about or ""),
                str(pronouns or ""),
                self._split_interests(str(interests or "")),
                bool(int(is_public or 0)),
            )

    async def upsert(
        self,
        guild_id: int,
        user_id: int,
        *,
        about: str | None = None,
        pronouns: str | None = None,
        interests: list[str] | None = None,
        is_public: bool | None = None,
    ) -> None:
        # Read current to support partial updates.
        current = await self.get(guild_id, user_id)
        about_v = current.about if about is None else (about or "")[:500]
        pronouns_v = current.pronouns if pronouns is None else (pronouns or "")[:32]
        interests_v = current.interests if interests is None else interests
        is_public_v = current.is_public if is_public is None else bool(is_public)

        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO profiles (guild_id, user_id, about, pronouns, interests, is_public, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, strftime('%s','now'))
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    about=excluded.about,
                    pronouns=excluded.pronouns,
                    interests=excluded.interests,
                    is_public=excluded.is_public,
                    updated_at=excluded.updated_at
                """
                ,
                (
                    int(guild_id),
                    int(user_id),
                    about_v,
                    pronouns_v,
                    self._join_interests(interests_v),
                    1 if is_public_v else 0,
                ),
            )
            await db.commit()
