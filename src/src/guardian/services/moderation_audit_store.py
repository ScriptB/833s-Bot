from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import aiosqlite

from .base import BaseService


@dataclass(frozen=True)
class AuditRecord:
    id: int
    guild_id: int
    correlation_id: str
    event_type: str
    user_id: int
    channel_id: Optional[int]
    message_id: Optional[int]
    rule_id: Optional[str]
    action_type: Optional[str]
    status: str
    created_at_iso: str
    details_json: str


class ModerationAuditStore(BaseService):
    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS moderation_audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              guild_id INTEGER NOT NULL,
              correlation_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              user_id INTEGER NOT NULL,
              channel_id INTEGER,
              message_id INTEGER,
              rule_id TEXT,
              action_type TEXT,
              status TEXT NOT NULL,
              created_at_iso TEXT NOT NULL,
              details_json TEXT NOT NULL
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_modaudit_corr ON moderation_audit(guild_id, correlation_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_modaudit_user ON moderation_audit(guild_id, user_id, id)")

    def _from_row(self, row: aiosqlite.Row) -> AuditRecord:
        return AuditRecord(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            correlation_id=str(row["correlation_id"]),
            event_type=str(row["event_type"]),
            user_id=int(row["user_id"]),
            channel_id=(int(row["channel_id"]) if row["channel_id"] is not None else None),
            message_id=(int(row["message_id"]) if row["message_id"] is not None else None),
            rule_id=(str(row["rule_id"]) if row["rule_id"] is not None else None),
            action_type=(str(row["action_type"]) if row["action_type"] is not None else None),
            status=str(row["status"]),
            created_at_iso=str(row["created_at_iso"]),
            details_json=str(row["details_json"]),
        )

    @property
    def _get_query(self) -> str:
        return "SELECT id, guild_id, correlation_id, event_type, user_id, channel_id, message_id, rule_id, action_type, status, created_at_iso, details_json FROM moderation_audit WHERE id = ?"

    async def add(
        self,
        *,
        guild_id: int,
        correlation_id: str,
        event_type: str,
        user_id: int,
        created_at_iso: str,
        status: str,
        details: dict[str, Any],
        channel_id: Optional[int] = None,
        message_id: Optional[int] = None,
        rule_id: Optional[str] = None,
        action_type: Optional[str] = None,
    ) -> int:
        details_json = json.dumps(details, separators=(",", ":"), ensure_ascii=False)
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                """
                INSERT INTO moderation_audit (
                  guild_id, correlation_id, event_type, user_id, channel_id, message_id,
                  rule_id, action_type, status, created_at_iso, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    correlation_id,
                    event_type,
                    user_id,
                    channel_id,
                    message_id,
                    rule_id,
                    action_type,
                    status,
                    created_at_iso,
                    details_json,
                ),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def recent_by_user(self, guild_id: int, user_id: int, limit: int = 20) -> list[AuditRecord]:
        limit = max(1, min(100, int(limit)))
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, guild_id, correlation_id, event_type, user_id, channel_id, message_id,
                       rule_id, action_type, status, created_at_iso, details_json
                FROM moderation_audit
                WHERE guild_id = ? AND user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (guild_id, user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [self._from_row(r) for r in rows]
