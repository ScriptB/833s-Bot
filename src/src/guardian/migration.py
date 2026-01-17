from __future__ import annotations

import logging
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import aiosqlite

log = logging.getLogger("guardian.migration")


class MigrationType(Enum):
    """Types of migrations."""
    SCHEMA_CHANGE = "schema_change"
    DATA_MIGRATION = "data_migration"
    CONFIG_UPDATE = "config_update"
    BREAKING_CHANGE = "breaking_change"


@dataclass
class Migration:
    """Represents a database migration."""
    version: str
    description: str
    migration_type: MigrationType
    up_sql: Optional[str] = None
    down_sql: Optional[str] = None
    up_function: Optional[Callable] = None
    down_function: Optional[Callable] = None
    depends_on: Optional[List[str]] = None
    breaking: bool = False


class MigrationManager:
    """Manages database migrations with safety and rollback capabilities."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.migrations: Dict[str, Migration] = {}
        self._register_standard_migrations()
    
    def _register_standard_migrations(self):
        """Register standard migrations for the bot."""
        
        # Panel store schema migration
        self.register_migration(Migration(
            version="1.0.0",
            description="Initial panel store schema",
            migration_type=MigrationType.SCHEMA_CHANGE,
            up_sql="""
                CREATE TABLE IF NOT EXISTS panels (
                    guild_id INTEGER NOT NULL,
                    panel_key TEXT NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    schema_version INTEGER DEFAULT 1,
                    last_deployed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, panel_key)
                );
                
                CREATE INDEX IF NOT EXISTS idx_panels_guild_id ON panels(guild_id);
                CREATE INDEX IF NOT EXISTS idx_panels_channel_id ON panels(channel_id);
                CREATE INDEX IF NOT EXISTS idx_panels_message_id ON panels(message_id);
            """,
            down_sql="DROP TABLE IF EXISTS panels;"
        ))
        
        # Role config store migration
        self.register_migration(Migration(
            version="1.1.0", 
            description="Add role configuration store",
            migration_type=MigrationType.SCHEMA_CHANGE,
            up_sql="""
                CREATE TABLE IF NOT EXISTS role_configs (
                    guild_id INTEGER NOT NULL,
                    role_name TEXT NOT NULL,
                    role_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    emoji TEXT,
                    description TEXT,
                    position INTEGER DEFAULT 0,
                    is_assignable BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, role_name)
                );
                
                CREATE INDEX IF NOT EXISTS idx_role_configs_guild_id ON role_configs(guild_id);
                CREATE INDEX IF NOT EXISTS idx_role_configs_category ON role_configs(category);
            """,
            down_sql="DROP TABLE IF EXISTS role_configs;"
        ))
        
        # Ticket system migration
        self.register_migration(Migration(
            version="1.2.0",
            description="Add ticket system tables",
            migration_type=MigrationType.SCHEMA_CHANGE,
            up_sql="""
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_number INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP,
                    closed_by_user_id INTEGER,
                    transcript TEXT,
                    subject TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_tickets_guild_id ON tickets(guild_id);
                CREATE INDEX IF NOT EXISTS idx_tickets_user_id ON tickets(user_id);
                CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
                CREATE INDEX IF NOT EXISTS idx_tickets_channel_id ON tickets(channel_id);
            """,
            down_sql="DROP TABLE IF EXISTS tickets;"
        ))
        
        # Migration tracking table
        self.register_migration(Migration(
            version="1.0.0-migration",
            description="Create migration tracking table",
            migration_type=MigrationType.SCHEMA_CHANGE,
            up_sql="""
                CREATE TABLE IF NOT EXISTS migrations (
                    version TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    rollback_sql TEXT,
                    migration_type TEXT NOT NULL,
                    breaking BOOLEAN DEFAULT FALSE
                );
                
                CREATE INDEX IF NOT EXISTS idx_migrations_applied_at ON migrations(applied_at);
            """,
            down_sql="DROP TABLE IF EXISTS migrations;"
        ))
    
    def register_migration(self, migration: Migration):
        """Register a new migration."""
        if migration.version in self.migrations:
            log.warning(f"Migration {migration.version} already registered, overwriting")
        
        self.migrations[migration.version] = migration
        log.info(f"Registered migration {migration.version}: {migration.description}")
    
    async def ensure_migration_table(self):
        """Ensure the migration tracking table exists."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    version TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    rollback_sql TEXT,
                    migration_type TEXT NOT NULL,
                    breaking BOOLEAN DEFAULT FALSE
                )
            """)
            await db.commit()
    
    async def get_applied_migrations(self) -> List[str]:
        """Get list of applied migration versions."""
        await self.ensure_migration_table()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT version FROM migrations ORDER BY version")
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
    
    async def is_migration_applied(self, version: str) -> bool:
        """Check if a migration has been applied."""
        applied = await self.get_applied_migrations()
        return version in applied
    
    async def apply_migration(self, migration: Migration) -> bool:
        """Apply a single migration."""
        if await self.is_migration_applied(migration.version):
            log.info(f"Migration {migration.version} already applied")
            return True
        
        log.info(f"Applying migration {migration.version}: {migration.description}")
        
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Start transaction
                await db.execute("BEGIN TRANSACTION")
                
                # Apply migration
                if migration.up_sql:
                    await db.executescript(migration.up_sql)
                
                if migration.up_function:
                    await migration.up_function(db)
                
                # Record migration
                await db.execute("""
                    INSERT INTO migrations (version, description, rollback_sql, migration_type, breaking)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    migration.version,
                    migration.description,
                    migration.down_sql,
                    migration.migration_type.value,
                    migration.breaking
                ))
                
                # Commit transaction
                await db.commit()
                
                log.info(f"Successfully applied migration {migration.version}")
                return True
                
            except Exception as e:
                # Rollback on error
                await db.rollback()
                log.error(f"Failed to apply migration {migration.version}: {e}")
                return False
    
    async def rollback_migration(self, version: str) -> bool:
        """Rollback a specific migration."""
        if not await self.is_migration_applied(version):
            log.warning(f"Migration {version} is not applied, cannot rollback")
            return False
        
        migration = self.migrations.get(version)
        if not migration:
            log.error(f"Migration {version} not found")
            return False
        
        if not migration.down_sql and not migration.down_function:
            log.warning(f"Migration {version} has no rollback defined")
            return False
        
        log.info(f"Rolling back migration {migration.version}")
        
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Start transaction
                await db.execute("BEGIN TRANSACTION")
                
                # Apply rollback
                if migration.down_sql:
                    await db.executescript(migration.down_sql)
                
                if migration.down_function:
                    await migration.down_function(db)
                
                # Remove migration record
                await db.execute("DELETE FROM migrations WHERE version = ?", (version,))
                
                # Commit transaction
                await db.commit()
                
                log.info(f"Successfully rolled back migration {migration.version}")
                return True
                
            except Exception as e:
                # Rollback on error
                await db.rollback()
                log.error(f"Failed to rollback migration {migration.version}: {e}")
                return False
    
    async def migrate_to_latest(self) -> Dict[str, Any]:
        """Apply all pending migrations."""
        applied = await self.get_applied_migrations()
        pending = [v for v in sorted(self.migrations.keys()) if v not in applied]
        
        results = {
            "applied": [],
            "failed": [],
            "skipped": [],
            "total_pending": len(pending)
        }
        
        if not pending:
            log.info("No pending migrations")
            return results
        
        log.info(f"Found {len(pending)} pending migrations")
        
        for version in pending:
            migration = self.migrations[version]
            
            # Check dependencies
            if migration.depends_on:
                missing_deps = [dep for dep in migration.depends_on if dep not in applied]
                if missing_deps:
                    log.warning(f"Skipping migration {version}: missing dependencies {missing_deps}")
                    results["skipped"].append(version)
                    continue
            
            # Apply migration
            success = await self.apply_migration(migration)
            if success:
                results["applied"].append(version)
                applied.append(version)
            else:
                results["failed"].append(version)
                # Stop on first failure for safety
                break
        
        log.info(f"Migration complete: applied={len(results['applied'])}, failed={len(results['failed'])}, skipped={len(results['skipped'])}")
        return results
    
    async def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status."""
        applied = await self.get_applied_migrations()
        all_versions = sorted(self.migrations.keys())
        pending = [v for v in all_versions if v not in applied]
        
        latest_applied = max(applied) if applied else None
        latest_available = max(all_versions) if all_versions else None
        
        return {
            "current_version": latest_applied,
            "latest_version": latest_available,
            "applied_count": len(applied),
            "pending_count": len(pending),
            "applied_migrations": applied,
            "pending_migrations": pending,
            "needs_migration": len(pending) > 0
        }


class ConfigManager:
    """Manages configuration with versioning and migration support."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.config_version = "1.0.0"
    
    async def ensure_config_table(self):
        """Ensure the config table exists."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guild_configs (
                    guild_id INTEGER PRIMARY KEY,
                    config_version TEXT NOT NULL,
                    config_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
    
    async def get_config(self, guild_id: int) -> Dict[str, Any]:
        """Get configuration for a guild with migration support."""
        await self.ensure_config_table()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT config_data, config_version FROM guild_configs WHERE guild_id = ?",
                (guild_id,)
            )
            row = await cursor.fetchone()
            
            if row:
                config_data, version = row
                config = self._parse_config(config_data)
                
                # Apply migrations if needed
                migrated_config = await self._migrate_config(config, version)
                if migrated_config != config:
                    # Save migrated config
                    await self.save_config(guild_id, migrated_config)
                
                return migrated_config
            else:
                # Return default config
                return self._get_default_config()
    
    async def save_config(self, guild_id: int, config: Dict[str, Any]):
        """Save configuration for a guild."""
        await self.ensure_config_table()
        
        config_json = self._serialize_config(config)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO guild_configs (guild_id, config_version, config_data, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (guild_id, self.config_version, config_json))
            await db.commit()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "version": self.config_version,
            "features": {
                "tickets_enabled": True,
                "roles_enabled": True,
                "panels_enabled": True
            },
            "ticket_config": {
                "category_name": "🎫 TICKETS",
                "support_roles": ["Support", "Moderator", "Admin", "Owner"],
                "transcript_enabled": True,
                "auto_close_days": 7
            },
            "role_categories": [
                {
                    "name": "games",
                    "display_name": "Game Roles",
                    "emoji": "🎮"
                },
                {
                    "name": "interests", 
                    "display_name": "Interest Roles",
                    "emoji": "🎯"
                }
            ]
        }
    
    def _parse_config(self, config_json: str) -> Dict[str, Any]:
        """Parse configuration JSON."""
        import json
        return json.loads(config_json)
    
    def _serialize_config(self, config: Dict[str, Any]) -> str:
        """Serialize configuration to JSON."""
        import json
        return json.dumps(config, separators=(',', ':'))
    
    async def _migrate_config(self, config: Dict[str, Any], from_version: str) -> Dict[str, Any]:
        """Migrate configuration from an older version."""
        # Add migration logic here as needed
        # For now, just ensure the config has the latest structure
        default_config = self._get_default_config()
        
        # Merge with defaults to ensure all keys exist
        migrated = default_config.copy()
        migrated.update(config)
        
        return migrated


# Global instances
migration_manager = None
config_manager = None


def initialize_migration_system(db_path: str):
    """Initialize the migration system."""
    global migration_manager, config_manager
    migration_manager = MigrationManager(db_path)
    config_manager = ConfigManager(db_path)


async def run_migrations(db_path: str) -> Dict[str, Any]:
    """Run all pending migrations."""
    if not migration_manager:
        initialize_migration_system(db_path)
    
    return await migration_manager.migrate_to_latest()


async def get_migration_status(db_path: str) -> Dict[str, Any]:
    """Get migration status."""
    if not migration_manager:
        initialize_migration_system(db_path)
    
    return await migration_manager.get_migration_status()


async def get_guild_config(guild_id: int, db_path: str) -> Dict[str, Any]:
    """Get guild configuration with migration support."""
    if not config_manager:
        initialize_migration_system(db_path)
    
    return await config_manager.get_config(guild_id)


async def save_guild_config(guild_id: int, config: Dict[str, Any], db_path: str):
    """Save guild configuration."""
    if not config_manager:
        initialize_migration_system(db_path)
    
    await config_manager.save_config(guild_id, config)
