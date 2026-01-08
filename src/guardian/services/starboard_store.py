from __future__ import annotations

import aiosqlite


class StarboardStore:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS starboard_config (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    threshold INTEGER NOT NULL DEFAULT 3
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS starboard_posts (
                    guild_id INTEGER NOT NULL,
                    source_message_id INTEGER NOT NULL,
                    starboard_message_id INTEGER NOT NULL,
                    stars INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, source_message_id)
                )
                """
            )
            await db.commit()

    async def set_config(self, guild_id: int, channel_id: int, threshold: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO starboard_config (guild_id, channel_id, threshold) VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id, threshold=excluded.threshold",
                (int(guild_id), int(channel_id), int(threshold)),
            )
            await db.commit()

    async def get_config(self, guild_id: int):
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT channel_id, threshold FROM starboard_config WHERE guild_id=?",
                (int(guild_id),),
            ) as cur:
                row = await cur.fetchone()
        return (int(row[0]), int(row[1])) if row else None

    async def upsert_post(self, guild_id: int, source_message_id: int, starboard_message_id: int, stars: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO starboard_posts (guild_id, source_message_id, starboard_message_id, stars) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(guild_id, source_message_id) DO UPDATE SET starboard_message_id=excluded.starboard_message_id, stars=excluded.stars",
                (int(guild_id), int(source_message_id), int(starboard_message_id), int(stars)),
            )
            await db.commit()

    async def get_post(self, guild_id: int, source_message_id: int):
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT starboard_message_id, stars FROM starboard_posts WHERE guild_id=? AND source_message_id=?",
                (int(guild_id), int(source_message_id)),
            ) as cur:
                row = await cur.fetchone()
        return (int(row[0]), int(row[1])) if row else None
