from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import aiosqlite

from .base import BaseService
from ..moderation.config_schema import default_config, validate_config


@dataclass(frozen=True)
class ModConfigPointers:
    guild_id: int
    published_revision: int
    draft_revision: int


class ModerationConfigStore(BaseService):
    """Versioned moderation config store.

    - `moderation_config_revisions`: append-only revisions
    - `moderation_config_state`: per guild pointers (draft/published)
    """

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS moderation_config_revisions (
              guild_id INTEGER NOT NULL,
              revision INTEGER NOT NULL,
              created_at_iso TEXT NOT NULL,
              created_by_user_id INTEGER,
              doc_json TEXT NOT NULL,
              PRIMARY KEY (guild_id, revision)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS moderation_config_state (
              guild_id INTEGER PRIMARY KEY,
              published_revision INTEGER NOT NULL,
              draft_revision INTEGER NOT NULL
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_modcfg_rev_guild ON moderation_config_revisions(guild_id, revision)"
        )

    def _from_row(self, row: aiosqlite.Row) -> Any:
        return row

    @property
    def _get_query(self) -> str:
        return "SELECT guild_id FROM moderation_config_state WHERE guild_id = ?"

    async def ensure_guild(self, guild_id: int, *, created_at_iso: str, created_by_user_id: Optional[int]) -> None:
        """Ensure guild has at least revision 1 and pointers."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT guild_id FROM moderation_config_state WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            if row:
                return

            doc = default_config()
            doc_json = json.dumps(doc, separators=(",", ":"), ensure_ascii=False)
            await db.execute(
                "INSERT INTO moderation_config_revisions (guild_id, revision, created_at_iso, created_by_user_id, doc_json) VALUES (?, 1, ?, ?, ?)",
                (guild_id, created_at_iso, created_by_user_id, doc_json),
            )
            await db.execute(
                "INSERT INTO moderation_config_state (guild_id, published_revision, draft_revision) VALUES (?, 1, 1)",
                (guild_id,),
            )
            await db.commit()

    async def get_pointers(self, guild_id: int) -> ModConfigPointers:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT guild_id, published_revision, draft_revision FROM moderation_config_state WHERE guild_id = ?",
                (guild_id,),
            )
            row = await cur.fetchone()
            if not row:
                raise RuntimeError("Moderation config not initialized")
            return ModConfigPointers(
                guild_id=int(row["guild_id"]),
                published_revision=int(row["published_revision"]),
                draft_revision=int(row["draft_revision"]),
            )

    async def get_doc(self, guild_id: int, revision: int) -> dict[str, Any]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT doc_json FROM moderation_config_revisions WHERE guild_id = ? AND revision = ?",
                (guild_id, revision),
            )
            row = await cur.fetchone()
            if not row:
                raise RuntimeError("Revision not found")
            return json.loads(row["doc_json"])

    async def get_published(self, guild_id: int) -> tuple[int, dict[str, Any]]:
        ptr = await self.get_pointers(guild_id)
        return ptr.published_revision, await self.get_doc(guild_id, ptr.published_revision)

    async def get_draft(self, guild_id: int) -> tuple[int, dict[str, Any]]:
        ptr = await self.get_pointers(guild_id)
        return ptr.draft_revision, await self.get_doc(guild_id, ptr.draft_revision)

    async def save_draft(self, guild_id: int, doc: dict[str, Any], *, created_at_iso: str, created_by_user_id: Optional[int]) -> int:
        issues = validate_config(doc)
        if issues:
            raise ValueError("Config validation failed: " + "; ".join(f"{i.path}: {i.message}" for i in issues[:10]))

        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            ptr = await self.get_pointers(guild_id)
            new_rev = max(ptr.draft_revision, ptr.published_revision) + 1
            doc_json = json.dumps(doc, separators=(",", ":"), ensure_ascii=False)
            await db.execute(
                "INSERT INTO moderation_config_revisions (guild_id, revision, created_at_iso, created_by_user_id, doc_json) VALUES (?, ?, ?, ?, ?)",
                (guild_id, new_rev, created_at_iso, created_by_user_id, doc_json),
            )
            await db.execute(
                "UPDATE moderation_config_state SET draft_revision = ? WHERE guild_id = ?",
                (new_rev, guild_id),
            )
            await db.commit()
            return new_rev

    async def publish(self, guild_id: int, *, published_by_user_id: Optional[int]) -> int:
        # Publish current draft
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            ptr = await self.get_pointers(guild_id)
            await db.execute(
                "UPDATE moderation_config_state SET published_revision = ? WHERE guild_id = ?",
                (ptr.draft_revision, guild_id),
            )
            await db.commit()
            return ptr.draft_revision

    async def rollback(self, guild_id: int, target_revision: int) -> None:
        # Validate exists
        _ = await self.get_doc(guild_id, target_revision)
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE moderation_config_state SET published_revision = ?, draft_revision = ? WHERE guild_id = ?",
                (target_revision, target_revision, guild_id),
            )
            await db.commit()
