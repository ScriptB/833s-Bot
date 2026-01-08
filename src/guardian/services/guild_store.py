from __future__ import annotations

import aiosqlite
import logging
from dataclasses import dataclass
from typing import Optional

from .cache import TTLCache

log = logging.getLogger("guardian.guild_store")


@dataclass(frozen=True)
class GuildConfig:
    guild_id: int
    welcome_channel_id: Optional[int]
    autorole_id: Optional[int]
    log_channel_id: Optional[int]

    anti_spam_max_msgs: int
    anti_spam_window_seconds: int
    anti_spam_timeout_seconds: int


class GuildStore:
    """SQLite-backed per-guild configuration with a TTL cache front.

    Includes basic schema migration to keep deployments painless.
    """

    def __init__(self, sqlite_path: str, cache_ttl_seconds: int) -> None:
        self._path = sqlite_path
        self._cache: TTLCache[int, GuildConfig] = TTLCache(default_ttl_seconds=cache_ttl_seconds)

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_config (
                  guild_id INTEGER PRIMARY KEY,
                  welcome_channel_id INTEGER NULL,
                  autorole_id INTEGER NULL,
                  log_channel_id INTEGER NULL,
                  anti_spam_max_msgs INTEGER NOT NULL DEFAULT 6,
                  anti_spam_window_seconds INTEGER NOT NULL DEFAULT 5,
                  anti_spam_timeout_seconds INTEGER NOT NULL DEFAULT 30
                )
                """
            )

            # Best-effort migrations for older databases
            cols = await self._get_columns(db, "guild_config")
            await self._add_column_if_missing(db, cols, "log_channel_id", "INTEGER NULL")
            await self._add_column_if_missing(db, cols, "anti_spam_max_msgs", "INTEGER NOT NULL DEFAULT 6")
            await self._add_column_if_missing(db, cols, "anti_spam_window_seconds", "INTEGER NOT NULL DEFAULT 5")
            await self._add_column_if_missing(db, cols, "anti_spam_timeout_seconds", "INTEGER NOT NULL DEFAULT 30")

            await db.commit()

        log.info("GuildStore initialized at %s", self._path)

    async def _get_columns(self, db: aiosqlite.Connection, table: str) -> set[str]:
        async with db.execute(f"PRAGMA table_info({table})") as cur:
            rows = await cur.fetchall()
        return {r[1] for r in rows}

    async def _add_column_if_missing(self, db: aiosqlite.Connection, cols: set[str], col: str, ddl: str) -> None:
        if col in cols:
            return
        await db.execute(f"ALTER TABLE guild_config ADD COLUMN {col} {ddl}")

    async def get(self, guild_id: int) -> GuildConfig:
        cached = self._cache.get(guild_id)
        if cached:
            return cached

        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                """
                SELECT welcome_channel_id, autorole_id, log_channel_id,
                       anti_spam_max_msgs, anti_spam_window_seconds, anti_spam_timeout_seconds
                FROM guild_config WHERE guild_id = ?
                """,
                (guild_id,),
            ) as cur:
                row = await cur.fetchone()

        if row is None:
            cfg = GuildConfig(
                guild_id=guild_id,
                welcome_channel_id=None,
                autorole_id=None,
                log_channel_id=None,
                anti_spam_max_msgs=6,
                anti_spam_window_seconds=5,
                anti_spam_timeout_seconds=30,
            )
            await self.upsert(cfg)
            return cfg

        cfg = GuildConfig(
            guild_id=guild_id,
            welcome_channel_id=row[0],
            autorole_id=row[1],
            log_channel_id=row[2],
            anti_spam_max_msgs=int(row[3]),
            anti_spam_window_seconds=int(row[4]),
            anti_spam_timeout_seconds=int(row[5]),
        )
        self._cache.set(guild_id, cfg)
        return cfg

    async def upsert(self, cfg: GuildConfig) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO guild_config (
                    guild_id, welcome_channel_id, autorole_id, log_channel_id,
                    anti_spam_max_msgs, anti_spam_window_seconds, anti_spam_timeout_seconds
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                  welcome_channel_id = excluded.welcome_channel_id,
                  autorole_id = excluded.autorole_id,
                  log_channel_id = excluded.log_channel_id,
                  anti_spam_max_msgs = excluded.anti_spam_max_msgs,
                  anti_spam_window_seconds = excluded.anti_spam_window_seconds,
                  anti_spam_timeout_seconds = excluded.anti_spam_timeout_seconds
                """,
                (
                    cfg.guild_id,
                    cfg.welcome_channel_id,
                    cfg.autorole_id,
                    cfg.log_channel_id,
                    int(cfg.anti_spam_max_msgs),
                    int(cfg.anti_spam_window_seconds),
                    int(cfg.anti_spam_timeout_seconds),
                ),
            )
            await db.commit()

        self._cache.set(cfg.guild_id, cfg)
