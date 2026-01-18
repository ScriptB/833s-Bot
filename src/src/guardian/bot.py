from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import Settings
from .constants import CACHE_TTL_SECONDS
from .database import initialize_database
from .error_handlers import setup_error_handlers
from .services.task_queue import QueuePolicy, TaskQueue
from .services.guild_store import GuildStore
from .services.stats import RuntimeStats
from .services.warnings_store import WarningsStore
from .services.levels_store import LevelsStore
from .services.levels_config_store import LevelsConfigStore
from .services.levels_ledger_store import LevelsLedgerStore
from .services.level_rewards_store import LevelRewardsStore
from .services.starboard_store import StarboardStore
from .services.server_config_store import ServerConfigStore
from .services.onboarding_store import OnboardingStore
from .services.drift_verifier import DriftVerifier
from .services.cases_store import CasesStore
from .services.reputation_store import ReputationStore
from .services.suggestions_store import SuggestionsStore
from .services.channel_bootstrapper import ChannelBootstrapper
from .services.bootstrap_state_store import BootstrapStateStore
from .services.status_reporter import StatusReporter
from .services.guild_logger import GuildLogger
from .services.panel_registry import PanelRegistry
from .startup_diagnostics import StartupDiagnostics
from .services.panel_store import PanelStore
from .permissions import validate_command_permissions
from .services.role_config_store import RoleConfigStore
from .services.profiles_store import ProfilesStore
from .services.titles_store import TitlesStore
from .services.root_store import RootStore
from .ui.persistent import register_all_views
from .observability import observability
from .migration import initialize_migration_system

log = logging.getLogger("guardian.bot")


import asyncio
from datetime import datetime


class _CommandSyncManager:
    def __init__(self, bot: "GuardianBot") -> None:
        self.bot = bot
        self._lock = asyncio.Lock()

    async def sync_startup(self) -> None:
        # Use sync_guild_id if set, otherwise dev_guild_id, else global
        if self.bot.settings.sync_guild_id:
            await self.sync_guild(self.bot.settings.sync_guild_id)
        elif self.bot.settings.dev_guild_id:
            await self.sync_guild(self.bot.settings.dev_guild_id)
        else:
            await self.sync_global()

    async def sync_global(self) -> None:
        async with self._lock:
            await self.bot.tree.sync()
            getattr(self.bot, "log", log).info("Commands synced globally")

            # Deterministic visibility check: ensure the tree isn't empty.
            cmds = self.bot.tree.get_commands()
            getattr(self.bot, "log", log).info("Tree commands loaded: %d", len(cmds))
            for c in cmds:
                getattr(self.bot, "log", log).info(" - /%s", c.name)

    async def sync_guild(self, guild_id: int) -> None:
        async with self._lock:
            guild = discord.Object(id=guild_id)
            await self.bot.tree.sync(guild=guild)
            getattr(self.bot, "log", log).info("Commands synced to guild %d", guild_id)

            # Deterministic visibility check: ensure the tree isn't empty.
            cmds = self.bot.tree.get_commands()
            getattr(self.bot, "log", log).info("Tree commands loaded: %d", len(cmds))
            for c in cmds:
                getattr(self.bot, "log", log).info(" - /%s", c.name)


class GuardianBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        self.log = log
        intents = discord.Intents.default()
        intents.members = True
        # We prefer slash commands; message content intent is optional.
        intents.message_content = bool(settings.message_content_intent)

        log.info("INTENTS: guilds=%s members=%s message_content=%s", intents.guilds, intents.members, intents.message_content)

        super().__init__(
            command_prefix=commands.when_mentioned_or("!", "?"),
            intents=intents,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
            help_command=None,
        )

        self.settings = settings
        self.owner_id = settings.owner_id
        self.stats = RuntimeStats()

        self.task_queue = TaskQueue(
            QueuePolicy(
                max_batch=settings.queue_max_batch,
                every_ms=settings.queue_every_ms,
                max_queue_size=settings.queue_max_size,
            ),
            stats=self.stats,
        )

        # Initialize all stores with centralized cache TTL
        cache_ttl = settings.cache_default_ttl_seconds or CACHE_TTL_SECONDS
        
        self.guild_store = GuildStore(settings.sqlite_path, cache_ttl)
        self.warnings_store = WarningsStore(settings.sqlite_path, cache_ttl)
        self.levels_store = LevelsStore(settings.sqlite_path, cache_ttl)
        self.levels_config_store = LevelsConfigStore(settings.sqlite_path, cache_ttl)
        self.levels_ledger_store = LevelsLedgerStore(settings.sqlite_path, cache_ttl)
        self.level_rewards_store = LevelRewardsStore(settings.sqlite_path, cache_ttl)
        self.starboard_store = StarboardStore(settings.sqlite_path, cache_ttl)
        self.server_config_store = ServerConfigStore(settings.sqlite_path, cache_ttl)
        self.onboarding_store = OnboardingStore(settings.sqlite_path, cache_ttl)
        self.cases_store = CasesStore(settings.sqlite_path, cache_ttl)
        self.reputation_store = ReputationStore(settings.sqlite_path, cache_ttl)
        self.suggestions_store = SuggestionsStore(settings.sqlite_path, cache_ttl)
        self.profiles_store = ProfilesStore(settings.sqlite_path, cache_ttl)
        self.titles_store = TitlesStore(settings.sqlite_path, cache_ttl)
        self.root_store = RootStore(settings.sqlite_path)
        self.panel_store = PanelStore(settings.sqlite_path)
        log.info("PanelStore loaded: %s", PanelStore.__name__)
        self.role_config_store = RoleConfigStore(settings.sqlite_path)
        self.bootstrap_state_store = BootstrapStateStore(settings.sqlite_path)
        
        # Initialize panel registry
        self.panel_registry = PanelRegistry(self, self.panel_store)
        
        # Initialize bot-specific services
        self.drift_verifier = DriftVerifier(self)
        self._sync_mgr = _CommandSyncManager(self)
        self.channel_bootstrapper = ChannelBootstrapper(self, self.bootstrap_state_store)
        self.status_reporter = StatusReporter(self)
        self.guild_logger = GuildLogger(self)

    async def setup_hook(self) -> None:
        start_time = datetime.utcnow()
        
        # Initialize all stores with centralized database initialization
        stores = [
            self.guild_store,
            self.warnings_store,
            self.levels_store,
            self.levels_config_store,
            self.levels_ledger_store,
            self.level_rewards_store,
            self.starboard_store,
            self.server_config_store,
            self.onboarding_store,
            self.cases_store,
            self.reputation_store,
            self.suggestions_store,
            self.profiles_store,
            self.titles_store,
            self.root_store,
            self.panel_store,
            self.role_config_store,
            self.bootstrap_state_store,
        ]
        
        await initialize_database(self.settings.sqlite_path, stores)
        observability.log_startup_event("database", "OK")
        
        # Initialize persistent UI framework
        register_all_views(self)
        log.info("Registered all persistent views")
        observability.log_startup_event("views_registered", "OK")
        
        # Initialize production systems
        initialize_migration_system(self.settings.sqlite_path)
        observability.log_startup_event("migration_system", "OK")
        
        # Initialize panel registry renderers (will be done by cogs)
        
        # Start background services
        # self.drift_verifier.start()  # DISABLED - Prevents automatic channel recreation
        self.task_queue.start()
        observability.log_startup_event("task_queue", "OK")
        
        # Setup error handlers
        await setup_error_handlers(self)
        observability.log_startup_event("error_handlers", "OK")

        loaded: list[str] = []
        failed: list[str] = []

        # Cogs are loaded defensively so one bad cog cannot prevent command registration.
        async def _load_cog(import_path: str, class_name: str) -> None:
            try:
                log.info("Loading cog: %s.%s", import_path, class_name)
                mod = __import__(import_path, fromlist=[class_name])
                cls = getattr(mod, class_name)
                await self.add_cog(cls(self))
                log.info("Loaded cog: %s.%s", import_path, class_name)
                loaded.append(f"{import_path}.{class_name}")
            except ModuleNotFoundError as e:
                log.error("Module not found for cog %s.%s: %s", import_path, class_name, e)
                failed.append(f"{import_path}.{class_name} (ModuleNotFoundError)")
            except AttributeError as e:
                log.error("Class %s not found in module %s: %s", class_name, import_path, e)
                # Log available attributes for debugging
                try:
                    mod = __import__(import_path, fromlist=[class_name])
                    available = [attr for attr in dir(mod) if not attr.startswith('_')]
                    log.error("Available attributes in %s: %s", import_path, available)
                except Exception as e:
                    log.error("Failed to import cog %s.%s: %s", import_path, class_name, e)
                failed.append(f"{import_path}.{class_name} (AttributeError)")
            except Exception as e:
                log.exception("Failed to load cog: %s.%s", import_path, class_name)
                failed.append(f"{import_path}.{class_name} ({type(e).__name__})")

        # Core configuration + server lifecycle
        await _load_cog("guardian.cogs.admin", "AdminCog")
        await _load_cog("guardian.cogs.setup_autoconfig", "SetupAutoConfigCog")
        await _load_cog("guardian.cogs.dm_cleanup", "DMCleanupCog")
        await _load_cog("guardian.cogs.admin_management", "AdminManagementCog")
        await _load_cog("guardian.cogs.root_management", "RootManagementCog")
        
        # Community + onboarding
        await _load_cog("guardian.cogs.welcome", "WelcomeCog")
        await _load_cog("guardian.cogs.onboarding", "OnboardingCog")
        # Legacy ticket panel implementation (kept optional to avoid overlapping systems).
        if getattr(self.settings, "legacy_tickets_enabled", False):
            await _load_cog("guardian.cogs.tickets", "TicketsCog")
        else:
            log.info("Legacy TicketsCog disabled; using TicketSystemCog only")
        await _load_cog("guardian.cogs.suggestions", "SuggestionsCog")


        # Core systems
        await _load_cog("guardian.cogs.levels_full", "LevelsCog")
        await _load_cog("guardian.cogs.starboard", "StarboardCog")
        await _load_cog("guardian.cogs.reputation", "ReputationCog")
        await _load_cog("guardian.cogs.utilities", "UtilitiesCog")

        # Community systems (non-moderation)
        if self.settings.profiles_enabled:
            await _load_cog("guardian.cogs.profiles", "ProfilesCog")
        if self.settings.titles_enabled:
            await _load_cog("guardian.cogs.titles", "TitlesCog")

        # Community vibe systems (non-moderation)
        if self.settings.prefix_commands_enabled and not self.intents.message_content:
            log.warning("PREFIX_COMMANDS_ENABLED but message_content intent is disabled; prefix commands will remain unavailable")
        elif self.settings.prefix_commands_enabled:
            await _load_cog("guardian.cogs.prefix_community", "PrefixCommunityCog")

        
        # Production-ready systems
        await _load_cog("guardian.cogs.setup_wizard", "SetupWizardCog")
        # Server template overhaul command (idempotent structural deploy)
        await _load_cog("guardian.cogs.server_template_overhaul", "ServerTemplateOverhaulCog")
        await _load_cog("guardian.cogs.ticket_system", "TicketSystemCog")
        await _load_cog("guardian.cogs.role_assignment", "RoleAssignmentCog")
        await _load_cog("guardian.cogs.activity_manager", "ActivityCog")
        await _load_cog("guardian.cogs.health_check", "HealthCheckCog")
        if getattr(self.settings, "reaction_roles_enabled", True):
            await _load_cog("guardian.cogs.reaction_roles_new", "ReactionRolesCog")
        else:
            log.info("Reaction roles disabled by settings; skipping ReactionRolesCog")
        
        # Persistent panels
        await _load_cog("guardian.cogs.verify_panel", "VerifyPanelCog")
        await _load_cog("guardian.cogs.role_panel", "RolePanelCog")
        await _load_cog("guardian.cogs.role_panel", "RoleSelectCog")
        

        log.info("Startup cog load summary: loaded=%d failed=%d", len(loaded), len(failed))
        if loaded:
            log.info("Successfully loaded cogs: %s", ", ".join(loaded))
        if failed:
            for name in failed:
                log.warning("Startup cog failed: %s", name)
        
        # Run startup diagnostics after cogs are loaded
        diagnostics = StartupDiagnostics(self)
        diagnostic_results = await diagnostics.run_diagnostics()
        
                
        # Repair all panels on startup
        repair_results = await self.panel_registry.repair_all_guilds_on_startup()
        log.info(f"Panel repair completed: {repair_results}")
        observability.log_startup_event("panel_registry_ready", "OK")
        
        await self._sync_mgr.sync_startup()
        log.info("Command sync complete")
        observability.log_startup_event("command_sync", "OK")
        observability.log_startup_event("command_sync_done", "OK")
        
        # Log startup complete with health summary
        startup_duration = (datetime.utcnow() - start_time).total_seconds() * 1000 if 'start_time' in locals() else 0
        observability.log_startup_complete(startup_duration)
        
        # Run startup self-check
        await self._run_startup_self_check()
        
        log.info("🚀 Guardian Bot startup complete - All systems operational")
    
    async def _run_startup_self_check(self):
        """Run comprehensive startup self-check."""
        try:
            log.info("🔍 Running startup self-check...")
            
            # Check critical cogs
            rr_enabled = bool(getattr(self.settings, "reaction_roles_enabled", True))

            critical_cogs = {
                'VerifyPanelCog': self.get_cog('VerifyPanelCog') is not None,
                'RolePanelCog': self.get_cog('RolePanelCog') is not None,
                'ActivityCog': self.get_cog('ActivityCog') is not None,
                'TicketSystemCog': self.get_cog('TicketSystemCog') is not None,
                'RoleAssignmentCog': self.get_cog('RoleAssignmentCog') is not None,
                'HealthCheckCog': self.get_cog('HealthCheckCog') is not None,
                # Reaction roles are optional. When disabled, they should not cause a startup failure.
                'ReactionRolesCog': (not rr_enabled) or (self.get_cog('ReactionRolesCog') is not None),
            }
            
            failed_cogs = [name for name, loaded in critical_cogs.items() if not loaded]
            if failed_cogs:
                log.error(f"❌ Self-check failed - Missing critical cogs: {failed_cogs}")
            else:
                log.info("✅ All critical cogs loaded successfully")
            
            # Check critical commands
            commands = list(self.tree.get_commands())
            critical_commands = {
                'verifypanel': any(cmd.name == 'verifypanel' for cmd in commands),
                'rolepanel': any(cmd.name == 'rolepanel' for cmd in commands),
                'roleselect': any(cmd.name == 'roleselect' for cmd in commands),
                'activity': any(cmd.name == 'activity' for cmd in commands),
                'ticket': any(cmd.name == 'ticket' for cmd in commands),
                'close': any(cmd.name == 'close' for cmd in commands),
                'roles': any(cmd.name == 'roles' for cmd in commands),
                'myroles': any(cmd.name == 'myroles' for cmd in commands),
                'health': any(cmd.name == 'health' for cmd in commands),
                'reactionroles': (not rr_enabled) or any(cmd.name == 'reactionroles' for cmd in commands),
            }
            
            failed_commands = [name for name, available in critical_commands.items() if not available]
            if failed_commands:
                log.error(f"❌ Self-check failed - Missing critical commands: {failed_commands}")
            else:
                log.info("✅ All critical commands registered successfully")
            
            # Check persistent views
            if hasattr(self, '_persistent_views_stats'):
                stats = self._persistent_views_stats
                if stats['succeeded'] > 0:
                    log.info(f"✅ Persistent views registered: {stats['succeeded']}/{stats['attempted']}")
                else:
                    log.error("❌ Self-check failed - No persistent views registered")
                
                if stats['failed'] > 0:
                    log.warning(f"⚠️ Some views failed to register: {stats['failed']}")
            
            # Check activity manager
            activity_cog = self.get_cog('ActivityCog')
            if activity_cog and hasattr(activity_cog, 'activity_manager'):
                log.info("✅ Activity manager is operational")
            else:
                log.error("❌ Self-check failed - Activity manager not available")
            
            # Validate command permissions
            actual = {cmd.name for cmd in commands}
            if validate_command_permissions(actual):
                log.info("✅ Command permissions validation passed")
            else:
                log.error("❌ Self-check failed - Command permissions validation failed")
            
            # Overall result
            if not failed_cogs and not failed_commands and validate_command_permissions(actual):
                log.info("🎉 Startup self-check passed - All systems operational")
            else:
                log.warning("⚠️ Startup self-check completed with issues - Some systems may be degraded")
                
        except Exception as e:
            log.error(f"❌ Startup self-check failed with exception: {e}")

    async def close(self) -> None:
        try:
            try:
                await self.drift_verifier.stop()
            except Exception as e:
                log.warning("Failed to stop drift verifier: %s", e)
            await self.task_queue.stop()
        finally:
            await super().close()

    async def on_command_error(self, context: commands.Context, exception: commands.CommandError) -> None:
        # Prefix/hybrid command errors
        log.warning("Command error: %s", exception, exc_info=exception)
        try:
            await context.reply("Something went wrong running that command.")
        except Exception as e:
            log.warning("Failed to send error reply: %s", e)


    async def on_ready(self):
        try:
            for g in list(self.guilds):
                # Bootstrap posting is manual-only to prevent redeploy spam. Use the dedicated bootstrap command if needed.
                # await self.channel_bootstrapper.ensure_first_posts(g)
        except Exception as e:
            log.warning("Failed to ensure first posts for guilds: %s", e)
