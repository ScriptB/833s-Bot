from __future__ import annotations

import aiosqlite
from dataclasses import dataclass


@dataclass(frozen=True)
class ServerConfig:
    guild_id: int
    welcome_channel_id: int | None
    welcome_enabled: bool
    autorole_id: int | None
    bot_commands_channel_id: int | None


class ServerConfigStore:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS server_config (
                    guild_id INTEGER PRIMARY KEY,
                    welcome_channel_id INTEGER NULL,
                    welcome_enabled INTEGER NOT NULL DEFAULT 0,
                    autorole_id INTEGER NULL,
                    bot_commands_channel_id INTEGER NULL
                )
                """
            )
            await db.commit()

    async def get(self, guild_id: int) -> ServerConfig:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT welcome_channel_id, welcome_enabled, autorole_id, bot_commands_channel_id FROM server_config WHERE guild_id=?",
                (int(guild_id),),
            ) as cur:
                row = await cur.fetchone()
        if not row:
            cfg = ServerConfig(int(guild_id), None, False, None, None)
            await self.upsert(cfg)
            return cfg
        return ServerConfig(
            int(guild_id),
            int(row[0]) if row[0] is not None else None,
            bool(row[1]),
            int(row[2]) if row[2] is not None else None,
            int(row[3]) if row[3] is not None else None,
        )

    async def upsert(self, cfg: ServerConfig) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO server_config (guild_id, welcome_channel_id, welcome_enabled, autorole_id, bot_commands_channel_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    welcome_channel_id=excluded.welcome_channel_id,
                    welcome_enabled=excluded.welcome_enabled,
                    autorole_id=excluded.autorole_id,
                    bot_commands_channel_id=excluded.bot_commands_channel_id
                """,
                (
                    int(cfg.guild_id),
                    int(cfg.welcome_channel_id) if cfg.welcome_channel_id is not None else None,
                    int(cfg.welcome_enabled),
                    int(cfg.autorole_id) if cfg.autorole_id is not None else None,
                    int(cfg.bot_commands_channel_id) if cfg.bot_commands_channel_id is not None else None,
                ),
            )
            await db.commit()
