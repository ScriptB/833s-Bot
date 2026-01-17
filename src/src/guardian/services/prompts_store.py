from __future__ import annotations

import aiosqlite
from dataclasses import dataclass
from typing import Sequence

from .base import BaseService


@dataclass(frozen=True)
class Prompt:
    prompt_id: int
    guild_id: int
    author_id: int
    text: str
    created_at: int


@dataclass(frozen=True)
class PromptAnswer:
    answer_id: int
    prompt_id: int
    guild_id: int
    author_id: int
    text: str
    created_at: int


class PromptsStore(BaseService):
    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS prompts (
                prompt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS prompt_answers (
                answer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                FOREIGN KEY(prompt_id) REFERENCES prompts(prompt_id)
            )
            """
        )
    
    def _from_row(self, row: aiosqlite.Row) -> None:
        # Prompts don't need a specific data class for now
        return None
    
    @property
    def _get_query(self) -> str:
        return "SELECT * FROM prompts WHERE prompt_id = ?"

    async def submit_prompt(self, guild_id: int, author_id: int, text: str) -> int:
        text = (text or "").strip()[:700]
        if not text:
            raise ValueError("empty prompt")
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "INSERT INTO prompts (guild_id, author_id, text) VALUES (?, ?, ?)",
                (int(guild_id), int(author_id), text),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def add_answer(self, guild_id: int, prompt_id: int, author_id: int, text: str) -> int:
        text = (text or "").strip()[:700]
        if not text:
            raise ValueError("empty answer")
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "INSERT INTO prompt_answers (prompt_id, guild_id, author_id, text) VALUES (?, ?, ?, ?)",
                (int(prompt_id), int(guild_id), int(author_id), text),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def get_current(self, guild_id: int) -> Prompt | None:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT prompt_id, guild_id, author_id, text, created_at FROM prompts WHERE guild_id=? ORDER BY prompt_id DESC LIMIT 1",
                (int(guild_id),),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return Prompt(int(row[0]), int(row[1]), int(row[2]), str(row[3]), int(row[4]))

    async def history(self, guild_id: int, limit: int = 10) -> Sequence[Prompt]:
        limit = max(1, min(int(limit), 25))
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT prompt_id, guild_id, author_id, text, created_at FROM prompts WHERE guild_id=? ORDER BY prompt_id DESC LIMIT ?",
                (int(guild_id), int(limit)),
            )
            rows = await cur.fetchall()
            return [Prompt(int(r[0]), int(r[1]), int(r[2]), str(r[3]), int(r[4])) for r in rows]

    async def answers_for(self, guild_id: int, prompt_id: int, limit: int = 20) -> Sequence[PromptAnswer]:
        limit = max(1, min(int(limit), 50))
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT answer_id, prompt_id, guild_id, author_id, text, created_at FROM prompt_answers WHERE guild_id=? AND prompt_id=? ORDER BY answer_id ASC LIMIT ?",
                (int(guild_id), int(prompt_id), int(limit)),
            )
            rows = await cur.fetchall()
            return [PromptAnswer(int(r[0]), int(r[1]), int(r[2]), int(r[3]), str(r[4]), int(r[5])) for r in rows]
