from __future__ import annotations

import logging

import discord
import aiosqlite
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
from .services.reminders_store import RemindersStore
from .services.starboard_store import StarboardStore
from .services.reaction_roles_store import ReactionRolesStore
from .services.giveaways_store import GiveawaysStore
from .services.economy_store import EconomyStore
from .services.server_config_store import ServerConfigStore
from .services.achievements_store import AchievementsStore
from .services.snapshot_store import SnapshotStore
from .services.onboarding_store import OnboardingStore
from .services.drift_verifier import DriftVerifier
from .services.cases_store import CasesStore
from .services.reputation_store import ReputationStore
from .services.suggestions_store import SuggestionsStore
from .services.channel_bootstrapper import ChannelBootstrapper
from .services.status_reporter import StatusReporter
from .services.guild_logger import GuildLogger
from .services.ambient_store import AmbientStore
from .services.profiles_store import ProfilesStore
from .services.titles_store import TitlesStore
from .services.prompts_store import PromptsStore
from .services.events_store import EventsStore
from .services.community_memory_store import CommunityMemoryStore
from .services.root_store import RootStore

log = logging.getLogger("guardian.bot")


import asyncio


class _CommandSyncManager:
    def __init__(self, bot: "GuardianBot") -> None:
        self.bot = bot
        self._lock = asyncio.Lock()

    async def sync_startup(self) -> None:
        # Check for optional guild sync setting
        sync_guild_id = getattr(self.bot.settings, 'sync_guild_id', None)
        if sync_guild_id:
            await self.sync_guild(sync_guild_id)
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

        self.log = log
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
        self.reminders_store = RemindersStore(settings.sqlite_path, cache_ttl)
        self.starboard_store = StarboardStore(settings.sqlite_path, cache_ttl)
        self.rr_store = ReactionRolesStore(settings.sqlite_path, cache_ttl)
        self.giveaways_store = GiveawaysStore(settings.sqlite_path, cache_ttl)
        self.economy_store = EconomyStore(settings.sqlite_path, cache_ttl)
        self.achievements_store = AchievementsStore(settings.sqlite_path, cache_ttl)
        self.server_config_store = ServerConfigStore(settings.sqlite_path, cache_ttl)
        self.snapshot_store = SnapshotStore(settings.sqlite_path, cache_ttl)
        self.onboarding_store = OnboardingStore(settings.sqlite_path, cache_ttl)
        self.cases_store = CasesStore(settings.sqlite_path, cache_ttl)
        self.reputation_store = ReputationStore(settings.sqlite_path, cache_ttl)
        self.suggestions_store = SuggestionsStore(settings.sqlite_path, cache_ttl)
        self.ambient_store = AmbientStore(settings.sqlite_path, cache_ttl)
        self.profiles_store = ProfilesStore(settings.sqlite_path, cache_ttl)
        self.titles_store = TitlesStore(settings.sqlite_path, cache_ttl)
        self.prompts_store = PromptsStore(settings.sqlite_path, cache_ttl)
        self.events_store = EventsStore(settings.sqlite_path, cache_ttl)
        self.community_memory_store = CommunityMemoryStore(settings.sqlite_path, cache_ttl)
        self.root_store = RootStore(settings.sqlite_path)
        
        # Initialize bot-specific services
        self.drift_verifier = DriftVerifier(self)
        self._sync_mgr = _CommandSyncManager(self)
        self.channel_bootstrapper = ChannelBootstrapper(self)
        self.status_reporter = StatusReporter(self)
        self.guild_logger = GuildLogger(self)

    async def setup_hook(self) -> None:
        # Initialize all stores with centralized database initialization
        stores = [
            self.guild_store,
            self.warnings_store,
            self.levels_store,
            self.levels_config_store,
            self.levels_ledger_store,
            self.level_rewards_store,
            self.reminders_store,
            self.starboard_store,
            self.rr_store,
            self.giveaways_store,
            self.economy_store,
            self.achievements_store,
            self.server_config_store,
            self.snapshot_store,
            self.onboarding_store,
            self.cases_store,
            self.reputation_store,
            self.suggestions_store,
            self.ambient_store,
            self.profiles_store,
            self.titles_store,
            self.prompts_store,
            self.events_store,
            self.community_memory_store,
            self.root_store,
        ]
        
        await initialize_database(self.settings.sqlite_path, stores)
        
        # Start background services
        # self.drift_verifier.start()  # DISABLED - Prevents automatic channel recreation
        self.task_queue.start()
        
        # Setup error handlers
        await setup_error_handlers(self)

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
                except Exception:
                    pass
                failed.append(f"{import_path}.{class_name} (AttributeError)")
            except Exception as e:
                log.exception("Failed to load cog: %s.%s", import_path, class_name)
                failed.append(f"{import_path}.{class_name} ({type(e).__name__})")

        # Core configuration + server lifecycle
        await _load_cog("guardian.cogs.admin", "AdminCog")
        await _load_cog("guardian.cogs.overhaul", "OverhaulCog")
        await _load_cog("guardian.cogs.corporate_overhaul", "CorporateOverhaulCog")
        await _load_cog("guardian.cogs.setup_autoconfig", "SetupAutoConfigCog")
        await _load_cog("guardian.cogs.dm_cleanup", "DMCleanupCog")
        await _load_cog("guardian.cogs.admin_management", "AdminManagementCog")
        await _load_cog("guardian.cogs.root_management", "RootManagementCog")
        await _load_cog("guardian.cogs.selftest", "SelfTestCog")

        # Community + onboarding
        await _load_cog("guardian.cogs.welcome", "WelcomeCog")
        await _load_cog("guardian.cogs.onboarding", "OnboardingCog")
        await _load_cog("guardian.cogs.tickets", "TicketsCog")
        await _load_cog("guardian.cogs.suggestions", "SuggestionsCog")
        await _load_cog("guardian.cogs.knowledge_base", "KnowledgeBaseCog")

        # Moderation + safety
        await _load_cog("guardian.cogs.moderation", "ModerationCog")
        await _load_cog("guardian.cogs.anti_raid", "AntiRaidCog")
        await _load_cog("guardian.cogs.audit_logs", "AuditLogsCog")

        # Engagement systems
        await _load_cog("guardian.cogs.levels_full", "LevelsCog")
        await _load_cog("guardian.cogs.reaction_roles", "ReactionRolesCog")
        await _load_cog("guardian.cogs.starboard", "StarboardCog")
        await _load_cog("guardian.cogs.giveaways", "GiveawaysCog")
        await _load_cog("guardian.cogs.reminders", "RemindersCog")
        await _load_cog("guardian.cogs.reputation", "ReputationCog")
        await _load_cog("guardian.cogs.achievements", "AchievementsCog")
        await _load_cog("guardian.cogs.economy", "EconomyCog")
        await _load_cog("guardian.cogs.voice_rooms", "VoiceRoomsCog")
        await _load_cog("guardian.cogs.fun", "FunCog")
        await _load_cog("guardian.cogs.utilities", "UtilitiesCog")

        # Community systems (non-moderation)
        if self.settings.profiles_enabled:
            await _load_cog("guardian.cogs.profiles", "ProfilesCog")
        if self.settings.titles_enabled:
            await _load_cog("guardian.cogs.titles", "TitlesCog")
        if self.settings.prompts_enabled:
            await _load_cog("guardian.cogs.prompts", "PromptsCog")
        if self.settings.events_enabled:
            await _load_cog("guardian.cogs.events", "EventsCog")
        if self.settings.community_memory_enabled:
            await _load_cog("guardian.cogs.community_memory", "CommunityMemoryCog")

        # Community vibe systems (non-moderation)
        if self.settings.prefix_commands_enabled and not self.intents.message_content:
            log.warning("PREFIX_COMMANDS_ENABLED but message_content intent is disabled; prefix commands will remain unavailable")
        elif self.settings.prefix_commands_enabled:
            await _load_cog("guardian.cogs.prefix_community", "PrefixCommunityCog")

        if self.settings.ambient_enabled:
            await _load_cog("guardian.cogs.ambient", "AmbientCog")

        # Diagnostics last
        await _load_cog("guardian.cogs.diagnostics", "DiagnosticsCog")

        log.info("Startup cog load summary: loaded=%d failed=%d", len(loaded), len(failed))
        if loaded:
            log.info("Successfully loaded cogs: %s", ", ".join(loaded))
        if failed:
            for name in failed:
                log.warning("Startup cog failed: %s", name)
        await self._sync_mgr.sync_startup()
        log.info("Command sync complete")

    async def close(self) -> None:
        try:
            try:
                await self.drift_verifier.stop()
            except Exception:
                pass
            await self.task_queue.stop()
        finally:
            await super().close()

    async def on_command_error(self, context: commands.Context, exception: commands.CommandError) -> None:
        # Prefix/hybrid command errors
        log.warning("Command error: %s", exception, exc_info=exception)
        try:
            await context.reply("Something went wrong running that command.")
        except Exception:
            pass


    async def on_ready(self):
        try:
            for g in list(self.guilds):
                await self.channel_bootstrapper.ensure_first_posts(g)
        except Exception:
            pass
