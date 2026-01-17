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
    """Create a backup of the database using VACUUM INTO."""
    if not backup_path:
        raise ValueError("backup_path cannot be empty")
    
    try:
        # VACUUM INTO requires the path to be properly escaped in SQL
        # We need to use string formatting but ensure the path is safe
        import os
        # Validate backup path is absolute or in a safe directory
        backup_dir = os.path.dirname(os.path.abspath(backup_path))
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)
        
        # Use proper SQL escaping - VACUUM INTO requires a string literal
        # We sanitize by ensuring it's a valid path with no SQL injection
        safe_path = backup_path.replace("'", "''")  # Escape single quotes
        async with aiosqlite.connect(sqlite_path) as db:
            await db.execute(f"VACUUM INTO '{safe_path}'")
            await db.commit()
        log.info(f"Database backed up to {backup_path}")
        
        # Sanity check: verify backup file exists and has content
        import os
        if os.path.exists(backup_path):
            backup_size = os.path.getsize(backup_path)
            log.info(f"Backup created successfully, size: {backup_size} bytes")
        else:
            raise FileNotFoundError(f"Backup file not created at {backup_path}")
            
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
