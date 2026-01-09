from __future__ import annotations

import logging
from typing import List

import aiosqlite

from .services.base import BaseService

log = logging.getLogger("guardian.database")


async def initialize_database(sqlite_path: str, stores: List[BaseService]) -> None:
    """Initialize the database with all stores."""
    try:
        # Apply SQLite optimizations
        async with aiosqlite.connect(sqlite_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute("PRAGMA cache_size=10000")
            await db.execute("PRAGMA temp_store=MEMORY")
            await db.execute("PRAGMA mmap_size=268435456")  # 256MB
            await db.commit()
        
        log.info("Applied SQLite optimizations")
        
        # Initialize all stores
        for store in stores:
            await store.init()
            log.info(f"Initialized {store.__class__.__name__}")
        
        log.info("Database initialization completed")
        
    except Exception as e:
        log.error(f"Failed to initialize database: {e}")
        raise


async def backup_database(sqlite_path: str, backup_path: str) -> None:
    """Create a backup of the database."""
    try:
        async with aiosqlite.connect(sqlite_path) as source:
            async with aiosqlite.connect(backup_path) as backup:
                await backup.execute("VACUUM INTO ?", (source,))
        log.info(f"Database backed up to {backup_path}")
    except Exception as e:
        log.error(f"Failed to backup database: {e}")
        raise


async def optimize_database(sqlite_path: str) -> None:
    """Optimize the database with VACUUM and ANALYZE."""
    try:
        async with aiosqlite.connect(sqlite_path) as db:
            await db.execute("ANALYZE")
            await db.execute("VACUUM")
            await db.commit()
        log.info("Database optimization completed")
    except Exception as e:
        log.error(f"Failed to optimize database: {e}")
        raise


async def get_database_info(sqlite_path: str) -> dict:
    """Get information about the database."""
    try:
        async with aiosqlite.connect(sqlite_path) as db:
            # Get page count and page size
            cursor = await db.execute("PRAGMA page_count")
            page_count = (await cursor.fetchone())[0]
            
            cursor = await db.execute("PRAGMA page_size")
            page_size = (await cursor.fetchone())[0]
            
            # Get table info
            cursor = await db.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0]: row[1] for row in await cursor.fetchall()}
            
            return {
                "size_bytes": page_count * page_size,
                "size_mb": (page_count * page_size) / (1024 * 1024),
                "page_count": page_count,
                "page_size": page_size,
                "table_count": len(tables),
                "tables": tables,
            }
    except Exception as e:
        log.error(f"Failed to get database info: {e}")
        raise
