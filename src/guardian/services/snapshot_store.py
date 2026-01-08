from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import aiosqlite


@dataclass(frozen=True)
class Snapshot:
    guild_id: int
    created_at: int
    kind: str
    payload_json: str


class SnapshotStore:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    guild_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (guild_id, created_at, kind)
                )
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_guild_kind ON snapshots (guild_id, kind, created_at)")
            await db.commit()

    async def put(self, guild_id: int, kind: str, payload: Dict[str, Any]) -> int:
        created_at = int(time.time())
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO snapshots (guild_id, created_at, kind, payload_json) VALUES (?, ?, ?, ?)",
                (int(guild_id), int(created_at), str(kind), payload_json),
            )
            await db.commit()
        return created_at

    async def latest(self, guild_id: int, kind: str) -> Optional[Snapshot]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT created_at, payload_json FROM snapshots WHERE guild_id=? AND kind=? ORDER BY created_at DESC LIMIT 1",
                (int(guild_id), str(kind)),
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        return Snapshot(int(guild_id), int(row[0]), str(kind), str(row[1]))
