from __future__ import annotations

import logging

import discord
import aiosqlite
from discord.ext import commands

from .config import Settings
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

log = logging.getLogger("guardian.bot")


import asyncio


class _CommandSyncManager:
    def __init__(self, bot: "GuardianBot") -> None:
        self.bot = bot
        self._lock = asyncio.Lock()

    async def sync_startup(self) -> None:
        # Global-only strategy: sync once during startup.
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
        self.stats = RuntimeStats()

        self.task_queue = TaskQueue(
            QueuePolicy(
                max_batch=settings.queue_max_batch,
                every_ms=settings.queue_every_ms,
                max_queue_size=settings.queue_max_size,
            ),
            stats=self.stats,
        )

        self.guild_store = GuildStore(settings.sqlite_path, settings.cache_default_ttl_seconds)
        self.warnings_store = WarningsStore(settings.sqlite_path)
        self.levels_store = LevelsStore(settings.sqlite_path)
        self.levels_config_store = LevelsConfigStore(settings.sqlite_path)
        self.levels_ledger_store = LevelsLedgerStore(settings.sqlite_path)
        self.level_rewards_store = LevelRewardsStore(settings.sqlite_path)
        self.reminders_store = RemindersStore(settings.sqlite_path)
        self.starboard_store = StarboardStore(settings.sqlite_path)
        self.rr_store = ReactionRolesStore(settings.sqlite_path)
        self.giveaways_store = GiveawaysStore(settings.sqlite_path)
        self.economy_store = EconomyStore(settings.sqlite_path)
        self.achievements_store = AchievementsStore(settings.sqlite_path)
        self.server_config_store = ServerConfigStore(settings.sqlite_path)
        self.snapshot_store = SnapshotStore(settings.sqlite_path)
        self.onboarding_store = OnboardingStore(settings.sqlite_path)
        self.drift_verifier = DriftVerifier(self)
        self._sync_mgr = _CommandSyncManager(self)
        self.cases_store = CasesStore(settings.sqlite_path)
        self.reputation_store = ReputationStore(settings.sqlite_path)
        self.suggestions_store = SuggestionsStore(settings.sqlite_path)
        self.ambient_store = AmbientStore(settings.sqlite_path)
        self.profiles_store = ProfilesStore(settings.sqlite_path)
        self.titles_store = TitlesStore(settings.sqlite_path)
        self.prompts_store = PromptsStore(settings.sqlite_path)
        self.events_store = EventsStore(settings.sqlite_path)
        self.community_memory_store = CommunityMemoryStore(settings.sqlite_path)
        self.channel_bootstrapper = ChannelBootstrapper(self)
        self.status_reporter = StatusReporter(self)
        self.guild_logger = GuildLogger(self)

    async def setup_hook(self) -> None:
        try:
            async with aiosqlite.connect(self.settings.sqlite_path) as db:
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA synchronous=NORMAL")
                await db.execute("PRAGMA foreign_keys=ON")
                await db.commit()
            log.info("SQLite pragmas applied (journal_mode=WAL)")
        except Exception:
            log.exception("Failed to apply SQLite pragmas")

        await self.guild_store.init()
        await self.warnings_store.init()
        await self.levels_store.init()
        await self.levels_config_store.init()
        await self.levels_ledger_store.init()
        await self.level_rewards_store.init()
        await self.reminders_store.init()
        await self.starboard_store.init()
        await self.rr_store.init()
        await self.giveaways_store.init()
        await self.economy_store.init()
        await self.achievements_store.init()
        await self.server_config_store.init()
        await self.snapshot_store.init()
        await self.onboarding_store.init()
        await self.cases_store.init()
        await self.reputation_store.init()
        await self.suggestions_store.init()
        await self.ambient_store.init()
        await self.profiles_store.init()
        await self.titles_store.init()
        await self.prompts_store.init()
        await self.events_store.init()
        await self.community_memory_store.init()
        self.drift_verifier.start()
        self.task_queue.start()

        loaded: list[str] = []
        failed: list[str] = []

        # Cogs are loaded defensively so one bad cog cannot prevent command registration.
        async def _load_cog(import_path: str, class_name: str) -> None:
            try:
                mod = __import__(import_path, fromlist=[class_name])
                cls = getattr(mod, class_name)
                await self.add_cog(cls(self))
                log.info("Loaded cog: %s.%s", import_path, class_name)
                loaded.append(f"{import_path}.{class_name}")
            except Exception:
                log.exception("Failed to load cog: %s.%s", import_path, class_name)
                failed.append(f"{import_path}.{class_name}")

        # Core configuration + server lifecycle
        await _load_cog("guardian.cogs.admin", "AdminCog")
        await _load_cog("guardian.cogs.corporate_overhaul", "CorporateOverhaulCog")

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
