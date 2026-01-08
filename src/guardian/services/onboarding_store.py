from __future__ import annotations

import aiosqlite
from dataclasses import dataclass


@dataclass(frozen=True)
class OnboardingState:
    guild_id: int
    user_id: int
    step: int
    language: str | None
    interests_json: str | None
    completed: bool


class OnboardingStore:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS onboarding (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    step INTEGER NOT NULL DEFAULT 0,
                    language TEXT NULL,
                    interests_json TEXT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            await db.commit()

    async def get(self, guild_id: int, user_id: int) -> OnboardingState:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT step, language, interests_json, completed FROM onboarding WHERE guild_id=? AND user_id=?",
                (int(guild_id), int(user_id)),
            ) as cur:
                row = await cur.fetchone()
        if not row:
            st = OnboardingState(int(guild_id), int(user_id), 0, None, None, False)
            await self.upsert(st)
            return st
        return OnboardingState(int(guild_id), int(user_id), int(row[0]), row[1], row[2], bool(row[3]))

    async def upsert(self, st: OnboardingState) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO onboarding (guild_id, user_id, step, language, interests_json, completed)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    step=excluded.step,
                    language=excluded.language,
                    interests_json=excluded.interests_json,
                    completed=excluded.completed
                """,
                (int(st.guild_id), int(st.user_id), int(st.step), st.language, st.interests_json, int(st.completed)),
            )
            await db.commit()
