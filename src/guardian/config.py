from __future__ import annotations

import os
from dataclasses import dataclass


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}

@dataclass(frozen=True)
class Settings:
    token: str
    dev_guild_id: int
    sync_guild_id: int
    owner_id: int
    queue_max_batch: int
    queue_every_ms: int
    queue_max_size: int
    cache_default_ttl_seconds: int
    sqlite_path: str
    log_level: str
    anti_spam_max_msgs: int
    anti_spam_window_seconds: int
    anti_spam_timeout_seconds: int
    # Community systems (non-moderation)
    # Prefix commands require message content intent in the Discord Developer Portal.
    prefix_commands_enabled: bool
    # Ambient replies are lightweight, rate-limited community interactions.
    ambient_enabled: bool
    # Ambient pings are opt-in and additionally rate-limited.
    ambient_pings_enabled: bool
    ambient_reply_chance_percent: int
    ambient_channel_mode: str  # "bot_commands_only" | "allowlist" | "all"
    ambient_per_channel_cooldown_seconds: int
    ambient_per_user_ping_cooldown_seconds: int
    ambient_daily_guild_cap: int
    ambient_min_level_for_pings: int
    profiles_enabled: bool
    titles_enabled: bool
    prompts_enabled: bool
    events_enabled: bool
    community_memory_enabled: bool
    # discord.py logs a warning (and prefix commands won't work reliably) when
    # message content intent is disabled. This project primarily uses slash
    # commands, but we default this on to avoid confusion.
    message_content_intent: bool = True

    # Channel name configuration (keeps the bot portable across server templates)
    verify_channel_name: str = "verify"
    tickets_channel_name: str = "tickets"
    mod_logs_channel_name: str = "mod-logs"
    role_panel_channel_name: str = "choose-your-games"
    reaction_roles_channel_name: str = "choose-your-games"
    bot_ops_channel_name: str = "admin-console"
    suggestions_channel_name: str = "general-chat"

    # Role name configuration
    verified_role_name: str = "Verified"
    member_role_name: str = "Member"
    quarantine_role_name: str = "Quarantine"

    # Bump reminder
    bump_reminder_enabled: bool = False
    bump_reminder_channel_name: str = "general-chat"
    bump_reminder_min_minutes: int = 20
    bump_reminder_max_minutes: int = 120
    bump_reminder_message: str = "Hey! Don't forget to use '!d Bump' to help the server grow!"






def load_settings() -> Settings:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is required")
    return Settings(
        token=token,
        dev_guild_id=_get_int("DEV_GUILD_ID", 0),
        sync_guild_id=_get_int("SYNC_GUILD_ID", 0),
        # Default to 0 to avoid accidentally granting owner powers to a random ID
        owner_id=_get_int("OWNER_ID", 0),
        queue_max_batch=_get_int("QUEUE_MAX_BATCH", 4),
        queue_every_ms=_get_int("QUEUE_EVERY_MS", 100),
        queue_max_size=_get_int("QUEUE_MAX_SIZE", 10_000),
        cache_default_ttl_seconds=_get_int("CACHE_DEFAULT_TTL_SECONDS", 120),
        sqlite_path=(os.getenv("SQLITE_PATH", "guardian.sqlite3").strip() or "guardian.sqlite3"),
        log_level=(os.getenv("LOG_LEVEL", "INFO").strip() or "INFO"),
        anti_spam_max_msgs=_get_int("ANTI_SPAM_MAX_MSGS", 6),
        anti_spam_window_seconds=_get_int("ANTI_SPAM_WINDOW_SECONDS", 5),
        anti_spam_timeout_seconds=_get_int("ANTI_SPAM_TIMEOUT_SECONDS", 30),
        message_content_intent=_get_bool("MESSAGE_CONTENT_INTENT", True),
        prefix_commands_enabled=_get_bool("PREFIX_COMMANDS_ENABLED", False),
        ambient_enabled=_get_bool("AMBIENT_ENABLED", False),
        ambient_pings_enabled=_get_bool("AMBIENT_PINGS_ENABLED", False),
        ambient_reply_chance_percent=_get_int("AMBIENT_REPLY_CHANCE_PERCENT", 2),
        ambient_channel_mode=(os.getenv("AMBIENT_CHANNEL_MODE", "bot_commands_only").strip() or "bot_commands_only"),
        ambient_per_channel_cooldown_seconds=_get_int("AMBIENT_PER_CHANNEL_COOLDOWN_SECONDS", 600),
        ambient_per_user_ping_cooldown_seconds=_get_int("AMBIENT_PER_USER_PING_COOLDOWN_SECONDS", 21600),
        ambient_daily_guild_cap=_get_int("AMBIENT_DAILY_GUILD_CAP", 30),
        ambient_min_level_for_pings=_get_int("AMBIENT_MIN_LEVEL_FOR_PINGS", 5),
        profiles_enabled=_get_bool("PROFILES_ENABLED", True),
        titles_enabled=_get_bool("TITLES_ENABLED", True),
        prompts_enabled=_get_bool("PROMPTS_ENABLED", True),
        events_enabled=_get_bool("EVENTS_ENABLED", True),
        community_memory_enabled=_get_bool("COMMUNITY_MEMORY_ENABLED", True),

        verify_channel_name=(os.getenv("VERIFY_CHANNEL_NAME", "verify").strip() or "verify"),
        tickets_channel_name=(os.getenv("TICKETS_CHANNEL_NAME", "tickets").strip() or "tickets"),
        mod_logs_channel_name=(os.getenv("MOD_LOGS_CHANNEL_NAME", "mod-logs").strip() or "mod-logs"),
        role_panel_channel_name=(os.getenv("ROLE_PANEL_CHANNEL_NAME", "choose-your-games").strip() or "choose-your-games"),
        reaction_roles_channel_name=(os.getenv("REACTION_ROLES_CHANNEL_NAME", "choose-your-games").strip() or "choose-your-games"),
        bot_ops_channel_name=(os.getenv("BOT_OPS_CHANNEL_NAME", "admin-console").strip() or "admin-console"),
        suggestions_channel_name=(os.getenv("SUGGESTIONS_CHANNEL_NAME", "general-chat").strip() or "general-chat"),

        verified_role_name=(os.getenv("VERIFIED_ROLE_NAME", "Verified").strip() or "Verified"),
        member_role_name=(os.getenv("MEMBER_ROLE_NAME", "Member").strip() or "Member"),
        quarantine_role_name=(os.getenv("QUARANTINE_ROLE_NAME", "Quarantine").strip() or "Quarantine"),

        bump_reminder_enabled=_get_bool("BUMP_REMINDER_ENABLED", False),
        bump_reminder_channel_name=(os.getenv("BUMP_REMINDER_CHANNEL_NAME", "general-chat").strip() or "general-chat"),
        bump_reminder_min_minutes=_get_int("BUMP_REMINDER_MIN_MINUTES", 20),
        bump_reminder_max_minutes=_get_int("BUMP_REMINDER_MAX_MINUTES", 120),
        bump_reminder_message=(os.getenv("BUMP_REMINDER_MESSAGE", "Hey! Don't forget to use '!d Bump' to help the server grow!").strip() or "Hey! Don't forget to use '!d Bump' to help the server grow!"),
    )
