from __future__ import annotations

import time

import aiosqlite

from .base import BaseService


class EconomyStore(BaseService):
    """SQLite-backed wallet + ledger with cooldown utilities.

    Tables:
      - economy_wallet: current balance + daily streak metadata
      - economy_ledger: immutable transaction history
    """

    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await self._create_tables(db)
            await db.commit()

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS economy_wallet (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                balance INTEGER NOT NULL DEFAULT 0,
                daily_streak INTEGER NOT NULL DEFAULT 0,
                daily_last_at INTEGER NOT NULL DEFAULT 0,
                work_last_at INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS economy_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL,
                meta TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_econ_ledger_g_u ON economy_ledger (guild_id, user_id, created_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_econ_wallet_g_b ON economy_wallet (guild_id, balance)")

    def _from_row(self, row: aiosqlite.Row) -> None:
        # Economy don't need a specific data class for now
        return None

    @property
    def _get_query(self) -> str:
        return "SELECT * FROM economy_wallet WHERE guild_id = ? AND user_id = ?"

    async def _ensure_row(self, db: aiosqlite.Connection, guild_id: int, user_id: int) -> None:
        now = int(time.time())
        await db.execute(
            """
            INSERT OR IGNORE INTO economy_wallet (guild_id, user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, user_id, now, now),
        )

    async def get_wallet(self, guild_id: int, user_id: int) -> tuple[int, int, int, int, int]:
        """Returns (balance, daily_streak, daily_last_at, work_last_at, updated_at)."""
        async with aiosqlite.connect(self._path) as db:
            await self._ensure_row(db, guild_id, user_id)
            cur = await db.execute(
                """
                SELECT balance, daily_streak, daily_last_at, work_last_at, updated_at
                FROM economy_wallet
                WHERE guild_id=? AND user_id=?
                """,
                (guild_id, user_id),
            )
            row = await cur.fetchone()
            await cur.close()
            assert row is not None
            return int(row[0]), int(row[1]), int(row[2]), int(row[3]), int(row[4])

    async def add(self, guild_id: int, user_id: int, amount: int, *, reason: str, meta: str = "") -> int:
        if amount == 0:
            bal, *_ = await self.get_wallet(guild_id, user_id)
            return bal

        now = int(time.time())
        async with aiosqlite.connect(self._path) as db:
            await self._ensure_row(db, guild_id, user_id)
            await db.execute(
                """
                UPDATE economy_wallet
                SET balance = balance + ?, updated_at = ?
                WHERE guild_id=? AND user_id=?
                """,
                (amount, now, guild_id, user_id),
            )
            await db.execute(
                """
                INSERT INTO economy_ledger (guild_id, user_id, amount, reason, meta, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, amount, reason, meta, now),
            )
            cur = await db.execute(
                "SELECT balance FROM economy_wallet WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            )
            row = await cur.fetchone()
            await cur.close()
            await db.commit()
            return int(row[0]) if row else 0

    async def set_daily_claim(self, guild_id: int, user_id: int, *, new_streak: int) -> None:
        now = int(time.time())
        async with aiosqlite.connect(self._path) as db:
            await self._ensure_row(db, guild_id, user_id)
            await db.execute(
                """
                UPDATE economy_wallet
                SET daily_streak=?, daily_last_at=?, updated_at=?
                WHERE guild_id=? AND user_id=?
                """,
                (new_streak, now, now, guild_id, user_id),
            )
            await db.commit()

    async def set_work_claim(self, guild_id: int, user_id: int) -> None:
        now = int(time.time())
        async with aiosqlite.connect(self._path) as db:
            await self._ensure_row(db, guild_id, user_id)
            await db.execute(
                """
                UPDATE economy_wallet
                SET work_last_at=?, updated_at=?
                WHERE guild_id=? AND user_id=?
                """,
                (now, now, guild_id, user_id),
            )
            await db.commit()

    async def top_balances(self, guild_id: int, limit: int = 10) -> list[tuple[int, int]]:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                """
                SELECT user_id, balance
                FROM economy_wallet
                WHERE guild_id=?
                ORDER BY balance DESC
                LIMIT ?
                """,
                (guild_id, int(limit)),
            )
            rows = await cur.fetchall()
            await cur.close()
            return [(int(r[0]), int(r[1])) for r in rows]
