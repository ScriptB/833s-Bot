from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands


log = logging.getLogger(__name__)


# NOTE: This cog implements the user's "DISCORD SERVER TEMPLATE — 833s" as an idempotent
# overhaul command. It creates/matches roles, categories, channels, and core guild settings.
# Where Discord API does not allow toggling a setting (e.g., Community Mode), it reports that
# in the command output.


@dataclass(frozen=True)
class RoleDef:
    name: str
    perms: discord.Permissions
    mentionable: bool = False


@dataclass(frozen=True)
class TextChannelDef:
    name: str
    read_only_for_verified: bool = False
    admin_only_send: bool = False
    threads_enabled: bool = False
    slowmode_seconds: int = 0


@dataclass(frozen=True)
class VoiceChannelDef:
    name: str


@dataclass(frozen=True)
class CategoryDef:
    name: str
    everyone_view: bool
    verified_view: bool
    verified_send: bool
    muted_view: bool
    muted_send: bool
    muted_speak: bool
    staff_only: bool = False
    text_channels: Tuple[TextChannelDef, ...] = ()
    voice_channels: Tuple[VoiceChannelDef, ...] = ()


def _perm(**kwargs: bool) -> discord.Permissions:
    p = discord.Permissions.none()
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


class ServerTemplateOverhaulCog(commands.Cog):
    """Overhaul the current guild to match the 833s server template."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------
    # Template definition
    # ------------------------

    def _role_defs(self) -> List[RoleDef]:
        # Staff
        owner = RoleDef(
            "Owner",
            discord.Permissions(administrator=True),
        )
        admin = RoleDef(
            "Admin",
            _perm(
                manage_guild=True,
                manage_roles=True,
                manage_channels=True,
                ban_members=True,
                kick_members=True,
                view_audit_log=True,
                manage_messages=True,
                manage_threads=True,
                mention_everyone=False,
            ),
        )
        moderator = RoleDef(
            "Moderator",
            _perm(
                kick_members=True,
                moderate_members=True,
                manage_messages=True,
                manage_threads=True,
                view_audit_log=True,
                ban_members=False,
                manage_roles=False,
            ),
        )
        helper = RoleDef(
            "Helper",
            _perm(
                manage_messages=True,
                moderate_members=True,
            ),
        )
        bot = RoleDef("Bot", discord.Permissions(administrator=True))

        # Core
        verified = RoleDef("Verified", discord.Permissions.none())
        member = RoleDef("Member", discord.Permissions.none())
        muted = RoleDef(
            "Muted",
            discord.Permissions.none(),
        )

        # Utility/pings
        games_ping = RoleDef("Games Ping", discord.Permissions.none(), mentionable=True)
        coding_ping = RoleDef("Coding Ping", discord.Permissions.none(), mentionable=True)
        events_ping = RoleDef("Events Ping", discord.Permissions.none(), mentionable=True)
        announcements_ping = RoleDef("Announcements Ping", discord.Permissions.none(), mentionable=True)

        # Activity (optional)
        regular = RoleDef("Regular", discord.Permissions.none())
        active = RoleDef("Active", discord.Permissions.none())
        veteran = RoleDef("Veteran", discord.Permissions.none())

        # Order here is the intended hierarchy top -> bottom.
        return [
            owner,
            admin,
            moderator,
            helper,
            bot,
            verified,
            member,
            muted,
            games_ping,
            coding_ping,
            events_ping,
            announcements_ping,
            regular,
            active,
            veteran,
        ]

    def _category_defs(self) -> List[CategoryDef]:
        return [
            CategoryDef(
                name="📌 START HERE",
                everyone_view=False,
                verified_view=True,
                verified_send=False,
                muted_view=True,
                muted_send=False,
                muted_speak=False,
                staff_only=False,
                text_channels=(
                    TextChannelDef("welcome", read_only_for_verified=True),
                    TextChannelDef("rules", read_only_for_verified=True),
                    TextChannelDef("roles"),
                    TextChannelDef("announcements", admin_only_send=True),
                    TextChannelDef("faq"),
                ),
            ),
            CategoryDef(
                name="💬 COMMUNITY",
                everyone_view=False,
                verified_view=True,
                verified_send=True,
                muted_view=True,
                muted_send=False,
                muted_speak=False,
                text_channels=(
                    TextChannelDef("general"),
                    TextChannelDef("off-topic"),
                    TextChannelDef("introductions"),
                    TextChannelDef("media"),
                    TextChannelDef("memes"),
                    TextChannelDef("suggestions", threads_enabled=True),
                    TextChannelDef("bot-commands"),
                ),
            ),
            CategoryDef(
                name="🎮 GAMING",
                everyone_view=False,
                verified_view=True,
                verified_send=True,
                muted_view=True,
                muted_send=False,
                muted_speak=False,
                text_channels=(
                    TextChannelDef("gaming-chat"),
                    TextChannelDef("lfg", slowmode_seconds=30),
                    TextChannelDef("clips-and-highlights"),
                    TextChannelDef("game-news"),
                ),
                voice_channels=(
                    VoiceChannelDef("🔊 Gaming VC 1"),
                    VoiceChannelDef("🔊 Gaming VC 2"),
                    VoiceChannelDef("🔊 AFK"),
                ),
            ),
            CategoryDef(
                name="🧠 CODING",
                everyone_view=False,
                verified_view=True,
                verified_send=True,
                muted_view=True,
                muted_send=False,
                muted_speak=False,
                text_channels=(
                    TextChannelDef("coding-chat"),
                    TextChannelDef("help-and-debug"),
                    TextChannelDef("projects", threads_enabled=True),
                    TextChannelDef("resources"),
                    TextChannelDef("showcase"),
                ),
            ),
            CategoryDef(
                name="🐍 SNAKES",
                everyone_view=False,
                verified_view=True,
                verified_send=True,
                muted_view=True,
                muted_send=False,
                muted_speak=False,
                text_channels=(
                    TextChannelDef("snake-chat"),
                    TextChannelDef("husbandry"),
                    TextChannelDef("photos-and-videos"),
                    TextChannelDef("care-guides"),
                    TextChannelDef("myths-and-facts"),
                ),
            ),
            CategoryDef(
                name="📅 EVENTS",
                everyone_view=False,
                verified_view=True,
                verified_send=False,
                muted_view=True,
                muted_send=False,
                muted_speak=False,
                text_channels=(
                    TextChannelDef("event-announcements", read_only_for_verified=True),
                    TextChannelDef("event-chat"),
                    TextChannelDef("event-signups"),
                ),
            ),
            CategoryDef(
                name="🛠 SUPPORT",
                everyone_view=False,
                verified_view=True,
                verified_send=True,
                muted_view=True,
                muted_send=False,
                muted_speak=False,
                text_channels=(
                    TextChannelDef("help-desk"),
                    TextChannelDef("report-an-issue"),
                ),
            ),
            CategoryDef(
                name="🔊 VOICE",
                everyone_view=False,
                verified_view=True,
                verified_send=False,
                muted_view=False,
                muted_send=False,
                muted_speak=False,
                text_channels=(),
                voice_channels=(
                    VoiceChannelDef("🔊 Chill VC"),
                    VoiceChannelDef("🔊 Music VC"),
                    VoiceChannelDef("🔊 Coding / Study VC"),
                ),
            ),
            CategoryDef(
                name="🔒 STAFF",
                everyone_view=False,
                verified_view=False,
                verified_send=False,
                muted_view=False,
                muted_send=False,
                muted_speak=False,
                staff_only=True,
                text_channels=(
                    TextChannelDef("staff-chat"),
                    TextChannelDef("mod-logs"),
                    TextChannelDef("admin-notes"),
                    TextChannelDef("reports-queue"),
                ),
            ),
        ]

    # ------------------------
    # Helpers
    # ------------------------

    @staticmethod
    def _role_by_name(guild: discord.Guild, name: str) -> Optional[discord.Role]:
        return discord.utils.get(guild.roles, name=name)

    @staticmethod
    def _category_by_name(guild: discord.Guild, name: str) -> Optional[discord.CategoryChannel]:
        return discord.utils.get(guild.categories, name=name)

    @staticmethod
    def _text_by_name(guild: discord.Guild, name: str) -> Optional[discord.TextChannel]:
        return discord.utils.get(guild.text_channels, name=name)

    @staticmethod
    def _voice_by_name(guild: discord.Guild, name: str) -> Optional[discord.VoiceChannel]:
        return discord.utils.get(guild.voice_channels, name=name)

    def _staff_roles(self, guild: discord.Guild) -> List[discord.Role]:
        names = ["Owner", "Admin", "Moderator", "Helper"]
        roles = [r for r in (self._role_by_name(guild, n) for n in names) if r]
        return roles

    def _build_overwrites(
        self,
        guild: discord.Guild,
        cat: CategoryDef,
        verified_role: discord.Role,
        muted_role: discord.Role,
    ) -> Dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
        ow: Dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {}

        everyone = guild.default_role
        staff_roles = self._staff_roles(guild)

        # Base overwrites
        ow[everyone] = discord.PermissionOverwrite(view_channel=cat.everyone_view)
        ow[verified_role] = discord.PermissionOverwrite(
            view_channel=cat.verified_view,
            send_messages=cat.verified_send,
            send_messages_in_threads=cat.verified_send,
            create_public_threads=cat.verified_send,
            create_private_threads=cat.verified_send,
        )
        ow[muted_role] = discord.PermissionOverwrite(
            view_channel=cat.muted_view,
            send_messages=cat.muted_send,
            add_reactions=False,
            speak=cat.muted_speak,
            connect=False,
        )

        if cat.staff_only:
            ow[everyone] = discord.PermissionOverwrite(view_channel=False)
            ow[verified_role] = discord.PermissionOverwrite(view_channel=False)
            ow[muted_role] = discord.PermissionOverwrite(view_channel=False)
            for sr in staff_roles:
                ow[sr] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        else:
            for sr in staff_roles:
                ow[sr] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        return ow

    # ------------------------
    # Command
    # ------------------------

    @app_commands.command(
        name="overhaul",
        description="Overhaul this server to match the 833s template (roles, channels, permissions, settings).",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def overhaul(self, interaction: discord.Interaction) -> None:
        # Ephemeral response so progress updates remain editable even if we delete the channel
        # the command was invoked from.
        await interaction.response.defer(ephemeral=True, thinking=True)

        async def _progress(step: int, total: int, label: str) -> None:
            # Simple text progress bar that can be edited in-place.
            width = 20
            filled = int((step / max(total, 1)) * width)
            bar = "█" * filled + "░" * (width - filled)
            await interaction.edit_original_response(content=f"[{bar}] {step}/{total}  {label}")

        async def _final(summary: str) -> None:
            await interaction.edit_original_response(content=summary)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("Guild context missing.", ephemeral=True)
            return

        results: List[str] = []
        warnings: List[str] = []

        # ------------------------
        # 0) NUKE CURRENT STRUCTURE
        # ------------------------
        # Requirement: delete ALL current channels, categories, and roles before creating template.
        # Reality: Discord prevents deleting @everyone, managed roles, and roles above/equal to the bot's top role.
        # We delete everything else and report anything we cannot delete.

        total_steps = 7
        step = 0

        # 0.1) Delete channels (includes categories as separate objects, so delete children first)
        step += 1
        await _progress(step, total_steps, "Deleting existing channels...")
        try:
            # Delete non-category channels first
            channels = sorted(
                [c for c in guild.channels if not isinstance(c, discord.CategoryChannel)],
                key=lambda c: (str(c.type), c.position),
            )
            for ch in channels:
                try:
                    await ch.delete(reason="833s template overhaul (nuke)")
                except discord.Forbidden:
                    warnings.append(f"Forbidden deleting channel: {getattr(ch, 'name', ch.id)}")
                except Exception as e:
                    warnings.append(f"Failed deleting channel {getattr(ch, 'name', ch.id)}: {type(e).__name__}")

            # Then delete categories
            cats = sorted(list(guild.categories), key=lambda c: c.position)
            for cat in cats:
                try:
                    await cat.delete(reason="833s template overhaul (nuke)")
                except discord.Forbidden:
                    warnings.append(f"Forbidden deleting category: {cat.name}")
                except Exception as e:
                    warnings.append(f"Failed deleting category {cat.name}: {type(e).__name__}")
        except Exception as e:
            warnings.append(f"Channel/category deletion pass failed: {type(e).__name__}")

        # 0.2) Delete roles
        step += 1
        await _progress(step, total_steps, "Deleting existing roles...")
        try:
            me = guild.me
            top_pos = me.top_role.position if me else 0
            roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)
            for role in roles:
                if role == guild.default_role:
                    continue
                if role.managed:
                    continue
                if role.position >= top_pos:
                    # Can't delete roles at/above bot.
                    continue
                try:
                    await role.delete(reason="833s template overhaul (nuke)")
                except discord.Forbidden:
                    warnings.append(f"Forbidden deleting role: {role.name}")
                except Exception as e:
                    warnings.append(f"Failed deleting role {role.name}: {type(e).__name__}")
        except Exception as e:
            warnings.append(f"Role deletion pass failed: {type(e).__name__}")

        # 1) Apply guild settings that are supported by the API
        step += 1
        await _progress(step, total_steps, "Applying server settings...")
        try:
            await guild.edit(
                verification_level=discord.VerificationLevel.medium,
                explicit_content_filter=discord.ContentFilter.all_members,
                default_notifications=discord.NotificationLevel.only_mentions,
                reason="833s template overhaul",
            )
            results.append("Guild settings updated: verification=Medium, explicit_filter=All Members, notifications=Mentions Only")
        except discord.Forbidden:
            warnings.append("Missing permission to edit guild settings.")
        except Exception as e:
            warnings.append(f"Failed to edit guild settings: {type(e).__name__}")

        # 2) Roles (create/update)
        step += 1
        await _progress(step, total_steps, "Creating roles...")
        role_defs = self._role_defs()
        created_roles = 0
        updated_roles = 0

        for rd in role_defs:
            role = self._role_by_name(guild, rd.name)
            if role is None:
                try:
                    role = await guild.create_role(
                        name=rd.name,
                        permissions=rd.perms,
                        mentionable=rd.mentionable,
                        reason="833s template overhaul",
                    )
                    created_roles += 1
                except discord.Forbidden:
                    warnings.append(f"Forbidden creating role: {rd.name}")
                except Exception as e:
                    warnings.append(f"Failed creating role {rd.name}: {type(e).__name__}")
            else:
                try:
                    changed = False
                    if role.permissions != rd.perms:
                        await role.edit(permissions=rd.perms, reason="833s template overhaul")
                        changed = True
                    if role.mentionable != rd.mentionable:
                        await role.edit(mentionable=rd.mentionable, reason="833s template overhaul")
                        changed = True
                    if changed:
                        updated_roles += 1
                except discord.Forbidden:
                    warnings.append(f"Forbidden updating role: {rd.name}")
                except Exception as e:
                    warnings.append(f"Failed updating role {rd.name}: {type(e).__name__}")

        # 2.1) Reorder roles to match hierarchy (best-effort)
        step += 1
        await _progress(step, total_steps, "Applying role order...")
        try:
            name_to_role = {r.name: r for r in guild.roles}
            desired = [name_to_role.get(rd.name) for rd in role_defs]
            desired = [r for r in desired if r is not None and r != guild.default_role]

            # Keep @everyone at bottom; move desired roles above it in specified order.
            # Discord positions: higher number = higher in list.
            # We'll set incremental positions from low to high for bottom->top.
            base = 1
            payload = {}
            for idx, role in enumerate(reversed(desired)):
                payload[role] = base + idx
            await guild.edit_role_positions(payload)
            results.append("Role ordering applied (best-effort).")
        except discord.Forbidden:
            warnings.append("Forbidden reordering roles (bot role likely too low).")
        except Exception:
            # Non-fatal. Many guilds disallow reordering depending on role placement.
            warnings.append("Role ordering could not be applied (non-fatal).")

        verified_role = self._role_by_name(guild, "Verified")
        muted_role = self._role_by_name(guild, "Muted")
        admin_role = self._role_by_name(guild, "Admin")

        if verified_role is None or muted_role is None:
            await interaction.followup.send(
                "Critical roles missing after attempted creation (Verified/Muted). Check bot permissions.",
                ephemeral=True,
            )
            return

        # 3) Categories + channels
        step += 1
        await _progress(step, total_steps, "Creating categories and channels...")
        cat_defs = self._category_defs()
        created_cats = 0
        created_text = 0
        created_voice = 0
        updated_overwrites = 0

        for cd in cat_defs:
            category = self._category_by_name(guild, cd.name)
            overwrites = self._build_overwrites(guild, cd, verified_role, muted_role)
            if category is None:
                try:
                    category = await guild.create_category(
                        cd.name,
                        overwrites=overwrites,
                        reason="833s template overhaul",
                    )
                    created_cats += 1
                except discord.Forbidden:
                    warnings.append(f"Forbidden creating category: {cd.name}")
                    continue
                except Exception as e:
                    warnings.append(f"Failed creating category {cd.name}: {type(e).__name__}")
                    continue
            else:
                try:
                    await category.edit(overwrites=overwrites, reason="833s template overhaul")
                    updated_overwrites += 1
                except Exception:
                    # Non-fatal
                    warnings.append(f"Failed updating overwrites for category: {cd.name}")

            # Text channels
            for tcd in cd.text_channels:
                chan = self._text_by_name(guild, tcd.name)
                if chan is None:
                    try:
                        chan = await guild.create_text_channel(
                            tcd.name,
                            category=category,
                            reason="833s template overhaul",
                        )
                        created_text += 1
                    except discord.Forbidden:
                        warnings.append(f"Forbidden creating text channel: {tcd.name}")
                        continue
                    except Exception as e:
                        warnings.append(f"Failed creating text channel {tcd.name}: {type(e).__name__}")
                        continue
                else:
                    # Ensure it is in the right category
                    if chan.category_id != (category.id if category else None):
                        try:
                            await chan.edit(category=category, reason="833s template overhaul")
                        except Exception:
                            warnings.append(f"Failed moving channel {tcd.name} into {cd.name}")

                # Apply per-channel overwrites
                try:
                    ow = dict(chan.overwrites)

                    # Read-only channels: prevent verified sending
                    if tcd.read_only_for_verified:
                        o = ow.get(verified_role, discord.PermissionOverwrite())
                        o.send_messages = False
                        o.add_reactions = False
                        o.create_public_threads = False
                        o.create_private_threads = False
                        o.send_messages_in_threads = False
                        ow[verified_role] = o

                    # Admin-only send (announcements): verified can view, but not send
                    if tcd.admin_only_send:
                        o = ow.get(verified_role, discord.PermissionOverwrite())
                        o.send_messages = False
                        o.send_messages_in_threads = False
                        ow[verified_role] = o
                        if admin_role:
                            oa = ow.get(admin_role, discord.PermissionOverwrite())
                            oa.send_messages = True
                            oa.send_messages_in_threads = True
                            ow[admin_role] = oa

                    await chan.edit(
                        slowmode_delay=tcd.slowmode_seconds,
                        reason="833s template overhaul",
                    )
                    # Discord does not expose a channel-level "threads enabled" toggle; it's permission-based.
                    if tcd.threads_enabled:
                        o = ow.get(verified_role, discord.PermissionOverwrite())
                        o.create_public_threads = True
                        o.send_messages_in_threads = True
                        ow[verified_role] = o
                    await chan.edit(overwrites=ow, reason="833s template overhaul")
                except Exception:
                    warnings.append(f"Failed applying settings/overwrites for channel: {tcd.name}")

            # Voice channels
            for vcd in cd.voice_channels:
                v = self._voice_by_name(guild, vcd.name)
                if v is None:
                    try:
                        await guild.create_voice_channel(
                            vcd.name,
                            category=category,
                            reason="833s template overhaul",
                        )
                        created_voice += 1
                    except discord.Forbidden:
                        warnings.append(f"Forbidden creating voice channel: {vcd.name}")
                    except Exception as e:
                        warnings.append(f"Failed creating voice channel {vcd.name}: {type(e).__name__}")
                else:
                    if v.category_id != (category.id if category else None):
                        try:
                            await v.edit(category=category, reason="833s template overhaul")
                        except Exception:
                            warnings.append(f"Failed moving voice channel {vcd.name} into {cd.name}")

        step += 1
        await _progress(step, total_steps, "Finalizing...")

        results.append(
            f"Roles: +{created_roles} created, {updated_roles} updated"
        )
        results.append(
            f"Structure: +{created_cats} categories, +{created_text} text, +{created_voice} voice; overwrites updated={updated_overwrites}"
        )

        # Community Mode cannot be enabled via bot API.
        warnings.append("Community Mode must be enabled manually in Server Settings (API does not toggle it).")

        # Build output
        out_lines = ["833s template overhaul complete."]
        out_lines.extend([f"- {r}" for r in results])
        if warnings:
            out_lines.append("Warnings:")
            out_lines.extend([f"- {w}" for w in warnings])

        await _final("\n".join(out_lines))


async def setup(bot: commands.Bot) -> None:
    # The project uses explicit add_cog in bot.py, but having setup keeps this extension compatible
    # if you ever switch to bot.load_extension.
    await bot.add_cog(ServerTemplateOverhaulCog(bot))
