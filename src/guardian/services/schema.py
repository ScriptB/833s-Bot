from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleSpec:
    name: str
    # Discord integer color (0xRRGGBB) or None
    color: int | None
    hoist: bool
    mentionable: bool
    kind: str  # staff/system/access/level/ping/interest/platform/timezone/status/bot


@dataclass(frozen=True)
class ChannelSpec:
    name: str
    kind: str  # text/voice
    topic: str | None = None
    slowmode: int = 0


@dataclass(frozen=True)
class CategorySpec:
    name: str
    channels: list[ChannelSpec]


@dataclass(frozen=True)
class ServerSchema:
    guild_name: str
    roles: list[RoleSpec]
    level_role_map: list[tuple[int, str]]
    categories: list[CategorySpec]


def canonical_schema() -> ServerSchema:
    # NOTE: "Owner" and "Co-Owner" are NOT created by the bot. Those are manual and should remain above the bot role.
    roles: list[RoleSpec] = [
        RoleSpec("Bot", 0x5865F2, True, False, "bot"),
        RoleSpec("Head Admin", 0xED4245, True, False, "staff"),
        RoleSpec("Admin", 0xE67E22, True, False, "staff"),
        RoleSpec("Moderator", 0xF1C40F, True, False, "staff"),
        RoleSpec("Support Staff", 0x57F287, True, False, "staff"),
        RoleSpec("Community Team", 0x3498DB, True, False, "staff"),

        RoleSpec("Quarantine", 0x2F3136, False, False, "system"),
        RoleSpec("Muted", 0x4F545C, False, False, "status"),
        RoleSpec("Verified Member", 0x1F8B4C, False, False, "access"),

        # Progression (cosmetic + lounge access only)
        RoleSpec("Level 0 – New", 0x99AAB5, False, False, "level"),
        RoleSpec("Level 5 – Regular", 0xCD7F32, False, False, "level"),
        RoleSpec("Level 10 – Contributor", 0xC0C0C0, False, False, "level"),
        RoleSpec("Level 20 – Veteran", 0xFFD700, False, False, "level"),
        RoleSpec("Level 35 – Elite", 0xE5E4E2, False, False, "level"),
        RoleSpec("Level 50 – Core", 0x5865F2, False, False, "level"),

        # Ping roles (opt-in)
        RoleSpec("Announcements Ping", 0x5865F2, False, True, "ping"),
        RoleSpec("Events Ping", 0x5865F2, False, True, "ping"),

        # Interest roles (opt-in)
        RoleSpec("Gaming Ping", 0x1ABC9C, False, True, "interest"),
        RoleSpec("Coding Ping", 0x9B59B6, False, True, "interest"),
        RoleSpec("Pets & Reptiles Ping", 0xE91E63, False, True, "interest"),
        RoleSpec("Caregiving & Life Admin Ping", 0x3498DB, False, True, "interest"),

        # Platform roles (opt-in)
        RoleSpec("PC", 0x99AAB5, False, False, "platform"),
        RoleSpec("Xbox", 0x107C10, False, False, "platform"),
        RoleSpec("PlayStation", 0x003791, False, False, "platform"),
        RoleSpec("Mobile", 0x99AAB5, False, False, "platform"),

        # Timezone roles (opt-in)
        RoleSpec("UK/Europe", 0x99AAB5, False, False, "timezone"),
        RoleSpec("Americas", 0x99AAB5, False, False, "timezone"),
        RoleSpec("APAC", 0x99AAB5, False, False, "timezone"),
    ]

    level_role_map: list[tuple[int, str]] = [
        (0, "Level 0 – New"),
        (5, "Level 5 – Regular"),
        (10, "Level 10 – Contributor"),
        (20, "Level 20 – Veteran"),
        (35, "Level 35 – Elite"),
        (50, "Level 50 – Core"),
    ]

    categories: list[CategorySpec] = [
        CategorySpec("SYSTEM / CORE", [
            ChannelSpec("bot-ops", "text", "Bot heartbeat + rebuild progress + diagnostics."),
            ChannelSpec("server-config", "text", "Read-only config snapshot (bot-posted)."),
            ChannelSpec("permission-audit", "text", "Drift reports + auto-fixes."),
            ChannelSpec("integrations", "text", "Integration notes (staff-only)."),
            ChannelSpec("incident-room", "text", "Emergency coordination (staff-only)."),
        ]),
        CategorySpec("ONBOARDING", [
            ChannelSpec("start-here", "text", "Start here. Complete verification in #verify."),
            ChannelSpec("rules", "text", "Rules and policies."),
            ChannelSpec("verify", "text", "Verification flow (buttons)."),
            ChannelSpec("help-verification", "text", "Quarantine-only help channel."),
        ]),
        CategorySpec("INFORMATION HUB", [
            ChannelSpec("announcements", "text", "Official announcements."),
            ChannelSpec("changelog", "text", "Updates + changelog."),
            ChannelSpec("community-guide", "text", "How the server works."),
            ChannelSpec("faq", "text", "Frequently asked questions."),
            ChannelSpec("server-status", "text", "Status / incidents / maintenance."),
            ChannelSpec("resources", "text", "Curated resources."),
            ChannelSpec("partners", "text", "Partners (optional)."),
        ]),
        CategorySpec("COMMUNITY", [
            ChannelSpec("general", "text", "General discussion."),
            ChannelSpec("introductions", "text", "Introduce yourself."),
            ChannelSpec("media", "text", "Images/videos (keep tidy).", slowmode=4),
            ChannelSpec("memes", "text", "Memes (optional).", slowmode=2),
            ChannelSpec("off-topic", "text", "Off-topic."),
            ChannelSpec("polls", "text", "Polls (threads encouraged).", slowmode=2),
            ChannelSpec("suggestions", "text", "Suggestions (use /suggest).", slowmode=4),
            ChannelSpec("bot-commands", "text", "Bot commands.", slowmode=2),
            ChannelSpec("contributors-lounge", "text", "Level 10+ lounge.", slowmode=2),
            ChannelSpec("veterans-lounge", "text", "Level 20+ lounge.", slowmode=2),
            ChannelSpec("elite-lounge", "text", "Level 35+ lounge.", slowmode=2),
            ChannelSpec("core-feedback", "text", "Level 50+ feedback.", slowmode=4),
        ]),
        CategorySpec("TOPICS", [
            ChannelSpec("gaming-chat", "text", "Gaming chat."),
            ChannelSpec("looking-for-group", "text", "LFG posts."),
            ChannelSpec("coding-chat", "text", "Coding/tech chat."),
            ChannelSpec("help-code", "text", "Thread-first coding help."),
            ChannelSpec("projects-showcase", "text", "Showcase projects."),
            ChannelSpec("pets-chat", "text", "Pets chat."),
            ChannelSpec("reptiles-care", "text", "Reptile care."),
            ChannelSpec("enclosure-setup", "text", "Enclosure setups.", slowmode=4),
            ChannelSpec("feeding-logs", "text", "Optional structured logs.", slowmode=6),
            ChannelSpec("life-admin", "text", "Life admin."),
            ChannelSpec("forms-and-benefits", "text", "General guidance (no personal data).", slowmode=6),
            ChannelSpec("routines-and-tools", "text", "Routines/tools."),
        ]),
        CategorySpec("SUPPORT", [
            ChannelSpec("support-start", "text", "Open tickets via buttons."),
            ChannelSpec("support-guidelines", "text", "Support rules."),
            ChannelSpec("ticket-transcripts", "text", "Ticket transcripts (staff read-only)."),
        ]),
        CategorySpec("EVENTS", [
            ChannelSpec("events", "text", "Event posts (read-only)."),
            ChannelSpec("event-chat", "text", "Event discussion."),
            ChannelSpec("calendar", "text", "Upcoming events (bot mirror)."),
        ]),
        CategorySpec("VOICE", [
            ChannelSpec("voice-text", "text", "Links while in voice.", slowmode=2),
            ChannelSpec("General Voice", "voice"),
            ChannelSpec("Gaming Voice 1", "voice"),
            ChannelSpec("Gaming Voice 2", "voice"),
            ChannelSpec("Focus / Co-Work", "voice"),
            ChannelSpec("AFK", "voice"),
        ]),
        CategorySpec("STAFF", [
            ChannelSpec("staff-announcements", "text", "Staff-only announcements."),
            ChannelSpec("staff-chat", "text", "Staff discussion."),
            ChannelSpec("mod-queue", "text", "Reports feed."),
            ChannelSpec("case-notes", "text", "Case notes (threads)."),
            ChannelSpec("staff-handbook", "text", "Handbook (read-only)."),
        ]),
        CategorySpec("LOGS / AUDIT", [
            ChannelSpec("audit-log", "text", "Audit events (bot mirror)."),
            ChannelSpec("message-log", "text", "Message delete/edit logs."),
            ChannelSpec("join-leave-log", "text", "Join/leave logs."),
            ChannelSpec("moderation-log", "text", "Timeout/ban/kick logs."),
            ChannelSpec("anti-raid-log", "text", "Anti-raid events."),
            ChannelSpec("ticket-log", "text", "Ticket open/close events."),
        ]),
        CategorySpec("ARCHIVE", [
            ChannelSpec("archived-announcements", "text", "Archived announcements."),
            ChannelSpec("archived-events", "text", "Archived events."),
            ChannelSpec("archived-projects", "text", "Archived projects."),
        ]),
    ]

    return ServerSchema(guild_name="833s", roles=roles, level_role_map=level_role_map, categories=categories)
