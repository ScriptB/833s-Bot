"""
Startup diagnostics for 833s Guardian bot fault tolerance.

This module provides comprehensive startup validation and logging
to ensure all critical systems are properly initialized.
"""

from __future__ import annotations

import logging
from typing import Any

import discord

log = logging.getLogger("guardian.startup_diagnostics")


class StartupDiagnostics:
    """Comprehensive startup validation and diagnostics."""
    
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.results: dict[str, Any] = {
            "loaded_cogs": [],
            "registered_commands": [],
            "progress_reporter_api": "unknown",
            "panel_store_schema": "unknown",
            "persistent_views_registered": False,
            "db_connected": False,
            "critical_failures": [],
            "warnings": []
        }
    
    async def run_diagnostics(self) -> dict[str, Any]:
        """Run comprehensive startup diagnostics."""
        log.info("🔍 Running startup diagnostics...")
        
        # Check loaded cogs
        await self._check_loaded_cogs()
        
        # Check registered commands
        await self._check_registered_commands()
        
                
        # Check PanelStore schema
        await self._check_panel_store_schema()
        
        # Check persistent views
        await self._check_persistent_views()
        
        # Check database connection
        await self._check_database_connection()
        
        # Log results
        self._log_results()
        
        return self.results
    
    async def _check_loaded_cogs(self):
        """Check which cogs are loaded."""
        try:
            loaded_cogs = list(self.bot.cogs.keys())
            self.results["loaded_cogs"] = loaded_cogs
            
            # Check for critical cogs - match bot's self-check
            critical_cogs = ["VerifyPanelCog", "RolePanelCog", "ActivityCog", "TicketSystemCog", "RoleAssignmentCog", "HealthCheckCog", "ReactionRolesCog"]
            missing_critical = [cog for cog in critical_cogs if cog not in loaded_cogs]
            
            if missing_critical:
                self.results["critical_failures"].append(f"Missing critical cogs: {missing_critical}")
            else:
                log.info(f"✅ All critical cogs loaded: {critical_cogs}")
                
        except Exception as e:
            self.results["critical_failures"].append(f"Failed to check loaded cogs: {e}")
    
    async def _check_registered_commands(self):
        """Check registered slash commands."""
        try:
            if hasattr(self.bot, 'tree'):
                commands = list(self.bot.tree.get_commands())
                self.results["registered_commands"] = [cmd.name for cmd in commands]
                
                # Check for critical commands (without slash prefix)
                critical_commands = ["verifypanel", "rolepanel", "activity", "ticket", "close", "roles", "myroles", "health", "setup", "reactionroles"]
                registered_names = [cmd.name for cmd in commands]
                missing_commands = [cmd for cmd in critical_commands if cmd not in registered_names]
                
                if missing_commands:
                    self.results["warnings"].append(f"Missing commands: {missing_commands}")
                else:
                    log.info(f"✅ All critical commands registered: {critical_commands}")
            else:
                self.results["warnings"].append("Bot tree not available")
                
        except Exception as e:
            self.results["warnings"].append(f"Failed to check registered commands: {e}")
    
        
    async def _check_panel_store_schema(self):
        """Check PanelStore schema version."""
        try:
            from .services.panel_store import PanelStore
            
            # Check required methods
            required_methods = ['init', 'upsert', 'get', 'delete', 'list_guild']
            available_methods = [method for method in required_methods if hasattr(PanelStore, method)]
            
            if len(available_methods) == len(required_methods):
                self.results["panel_store_schema"] = "v1.0"
                log.info("✅ PanelStore schema v1.0 available")
            else:
                missing = set(required_methods) - set(available_methods)
                self.results["critical_failures"].append(f"PanelStore missing methods: {missing}")
                
        except ImportError as e:
            self.results["critical_failures"].append(f"PanelStore import failed: {e}")
        except Exception as e:
            self.results["warnings"].append(f"Failed to check PanelStore schema: {e}")
    
    async def _check_persistent_views(self):
        """Check if persistent views are registered."""
        try:
            # Use the registration stats from the persistent UI module
            if hasattr(self.bot, '_persistent_views_stats'):
                stats = self.bot._persistent_views_stats
                self.results["persistent_views_registered"] = stats['succeeded'] > 0
                if stats['succeeded'] > 0:
                    log.info(f"✅ Persistent views registered: {stats['succeeded']} views")
                else:
                    self.results["warnings"].append("No persistent views registered")
            else:
                # Fallback check
                persistent_views_count = 0
                if hasattr(self.bot, 'persistent_views'):
                    persistent_views_count = len(self.bot.persistent_views)
                
                self.results["persistent_views_registered"] = persistent_views_count > 0
                if persistent_views_count > 0:
                    log.info(f"✅ Persistent views registered: {persistent_views_count} views")
                else:
                    self.results["warnings"].append("No persistent views registered")
                
        except Exception as e:
            self.results["warnings"].append(f"Failed to check persistent views: {e}")
    
    async def _check_database_connection(self):
        """Check database connection."""
        try:
            if hasattr(self.bot, 'panel_store'):
                # Try a simple database operation
                await self.bot.panel_store.init()
                self.results["db_connected"] = True
                log.info("✅ Database connected and initialized")
            else:
                self.results["critical_failures"].append("PanelStore not available")
                
        except Exception as e:
            self.results["critical_failures"].append(f"Database connection failed: {e}")
    
    def _log_results(self):
        """Log diagnostic results."""
        log.info("📊 Startup Diagnostics Results:")
        log.info(f"  Loaded Cogs: {len(self.results['loaded_cogs'])}")
        log.info(f"  Registered Commands: {len(self.results['registered_commands'])}")
        log.info(f"  ProgressReporter API: {self.results['progress_reporter_api']}")
        log.info(f"  PanelStore Schema: {self.results['panel_store_schema']}")
        log.info(f"  Persistent Views: {self.results['persistent_views_registered']}")
        log.info(f"  DB Connected: {self.results['db_connected']}")
        
        if self.results["critical_failures"]:
            log.error(f"❌ Critical Failures: {self.results['critical_failures']}")
        
        if self.results["warnings"]:
            log.warning(f"⚠️ Warnings: {self.results['warnings']}")
        
        if not self.results["critical_failures"] and not self.results["warnings"]:
            log.info("🎉 All systems operational!")
    
    
