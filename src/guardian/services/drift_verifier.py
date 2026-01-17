from __future__ import annotations

import asyncio
from typing import Optional

import discord

from .schema import canonical_schema
from .schema_builder import SchemaBuilder


class DriftVerifier:
    def __init__(self, bot: discord.Client, interval_seconds: int = 3600) -> None:
        self.bot = bot
        self.interval = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await self._task
            except Exception:
                pass

    async def _run(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(self.interval)
            for guild in list(getattr(self.bot, "guilds", [])):
                try:
                    schema = canonical_schema()
                    builder = SchemaBuilder(self.bot)
                    roles = await builder.ensure_roles(guild, schema)
                    await builder.ensure_categories_channels(guild, schema, roles)
                except Exception:
                    continue
