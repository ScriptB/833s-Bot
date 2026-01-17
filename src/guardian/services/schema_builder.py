from __future__ import annotations

import asyncio
import discord
from typing import Dict, Iterable

from .schema import ServerSchema
from ..lookup import find_text_channel, find_voice_channel, find_category


def _ow(**kwargs) -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(**kwargs)


def _deny_view() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(view_channel=False)


def _allow_readonly() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True, add_reactions=True)


def _allow_chat() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, add_reactions=True, embed_links=True)


class SchemaBuilder:
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot

    async def nuke_guild(self, guild: discord.Guild, *, status=None) -> None:
        # Delete channels/categories first (fast + safe)
        # Note: Discord disallows deleting the system channels in certain cases; we skip failures.
        chans = list(guild.channels)
        # Delete children first, then categories
        children = [c for c in chans if not isinstance(c, discord.CategoryChannel)]
        cats = [c for c in chans if isinstance(c, discord.CategoryChannel)]

        for i, ch in enumerate(children, 1):
            if status:
                await status.update(guild, i, f"Nuking channels ({i}/{len(children)})")
            try:
                await ch.delete(reason="833s Guardian overhaul (nuke)")
            except discord.HTTPException:
                await asyncio.sleep(0.2)
            await asyncio.sleep(0.25)

        for i, cat in enumerate(cats, 1):
            if status:
                await status.update(guild, i, f"Nuking categories ({i}/{len(cats)})")
            try:
                await cat.delete(reason="833s Guardian overhaul (nuke)")
            except discord.HTTPException:
                await asyncio.sleep(0.2)
            await asyncio.sleep(0.25)

        # Delete roles (keep @everyone, managed roles, and roles above bot)
        me = guild.me
        if me is None:
            return
        bot_top = me.top_role

        roles = sorted(list(guild.roles), key=lambda r: r.position, reverse=True)
        for idx, r in enumerate(roles, 1):
            if r.is_default() or r.managed:
                continue
            # Can't delete roles >= bot top
            if r >= bot_top:
                continue
            try:
                await r.delete(reason="833s Guardian overhaul (nuke)")
            except discord.HTTPException:
                await asyncio.sleep(0.2)
            await asyncio.sleep(0.2)

    async def ensure_roles(self, guild: discord.Guild, schema: ServerSchema, *, status=None) -> Dict[str, discord.Role]:
        # Create roles bottom-up to preserve hierarchy
        existing = {r.name: r for r in guild.roles}
        created: Dict[str, discord.Role] = {}

        # Resolve desired order: as provided in schema.roles (top->bottom). We'll create reversed.
        for i, spec in enumerate(reversed(schema.roles), 1):
            if status:
                await status.update(guild, i, f"Ensuring roles ({i}/{len(schema.roles)})")
            role = existing.get(spec.name)
            if role is None:
                try:
                    role = await guild.create_role(
                        name=spec.name,
                        colour=discord.Colour(spec.color) if spec.color is not None else discord.Colour.default(),
                        hoist=bool(spec.hoist),
                        mentionable=bool(spec.mentionable),
                        reason="833s Guardian schema apply",
                    )
                    created[spec.name] = role
                    existing[spec.name] = role
                except discord.HTTPException:
                    await asyncio.sleep(0.5)
                    continue
            else:
                try:
                    await role.edit(
                        colour=discord.Colour(spec.color) if spec.color is not None else discord.Colour.default(),
                        hoist=bool(spec.hoist),
                        mentionable=bool(spec.mentionable),
                        reason="833s Guardian schema apply",
                    )
                except discord.HTTPException:
                    pass

            await asyncio.sleep(0.2)

        # Try to position bot role under owner/co-owner (manual) by moving it near top of manageable roles.
        bot_role = existing.get("Bot")
        me = guild.me
        if bot_role and me:
            try:
                # ensure the bot's *managed* role stays; "Bot" role is separate. This is fine.
                pass
            except Exception:
                pass

        # Return map
        return {name: role for name, role in existing.items() if name in {s.name for s in schema.roles}}

    def _role(self, roles: Dict[str, discord.Role], name: str) -> discord.Role | None:
        r = roles.get(name)
        return r if isinstance(r, discord.Role) else None

    async def ensure_categories_channels(self, guild: discord.Guild, schema: ServerSchema, roles: Dict[str, discord.Role], *, status=None) -> None:
        everyone = guild.default_role
        verified = self._role(roles, "Verified Member")
        quarantine = self._role(roles, "Quarantine")
        muted = self._role(roles, "Muted")

        head_admin = self._role(roles, "Head Admin")
        admin = self._role(roles, "Admin")
        moderator = self._role(roles, "Moderator")
        support = self._role(roles, "Support Staff")
        community = self._role(roles, "Community Team")
        bot_role = self._role(roles, "Bot")

        lvl10 = self._role(roles, "Level 10 – Contributor")
        lvl20 = self._role(roles, "Level 20 – Veteran")
        lvl35 = self._role(roles, "Level 35 – Elite")
        lvl50 = self._role(roles, "Level 50 – Core")

        staff_roles = [r for r in [head_admin, admin, moderator, support, community] if r]
        staff_manage = [r for r in [head_admin, admin] if r]

        def cat_overwrites(cat_name: str) -> Dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
            ow: Dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {everyone: _deny_view()}
            if bot_role:
                ow[bot_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            if cat_name in {"ONBOARDING"}:
                # Everyone can view onboarding; quarantine can speak in verify/help only via channel overrides
                ow[everyone] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)
                if verified:
                    ow[verified] = discord.PermissionOverwrite(view_channel=False)
                for r in staff_roles:
                    ow[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
                return ow

            if cat_name in {"SYSTEM / CORE", "STAFF", "LOGS / AUDIT"}:
                # Hidden to members
                for r in staff_roles:
                    ow[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
                # Support can read logs if desired; keep staff only.
                return ow

            if verified:
                ow[verified] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, add_reactions=True, embed_links=True, attach_files=True, use_application_commands=True)

            if muted:
                ow[muted] = discord.PermissionOverwrite(view_channel=True, send_messages=False, add_reactions=False)

            return ow

        # Ensure categories in locked order
        existing_cats = {c.name: c for c in guild.categories}
        for idx, cat_spec in enumerate(schema.categories, 1):
            if status:
                await status.update(guild, idx, f"Ensuring categories ({idx}/{len(schema.categories)})")
            cat = existing_cats.get(cat_spec.name)
            if cat is None:
                try:
                    cat = await guild.create_category(name=cat_spec.name, reason="833s Guardian schema apply")
                    existing_cats[cat_spec.name] = cat
                except discord.HTTPException:
                    await asyncio.sleep(0.5)
                    continue

            # apply category overwrites
            key = "ONBOARDING" if cat_spec.name == "ONBOARDING" else cat_spec.name
            try:
                await cat.edit(overwrites=cat_overwrites(key), reason="833s Guardian schema apply")
            except discord.HTTPException:
                pass

            await asyncio.sleep(0.25)

            # channels
            for ch_i, ch_spec in enumerate(cat_spec.channels, 1):
                if status:
                    await status.update(guild, ch_i, f"Ensuring channels in {cat_spec.name} ({ch_i}/{len(cat_spec.channels)})")
                if ch_spec.kind == "text":
                    ch = find_text_channel(guild, ch_spec.name)
                    if not ch:
                        try:
                            ch = await guild.create_text_channel(
                                name=ch_spec.name,
                                category=cat,
                                topic=ch_spec.topic,
                                slowmode_delay=int(ch_spec.slowmode),
                                reason="833s Guardian schema apply",
                            )
                        except discord.HTTPException:
                            await asyncio.sleep(0.5)
                            continue
                    else:
                        try:
                            await ch.edit(category=cat, topic=ch_spec.topic, slowmode_delay=int(ch_spec.slowmode), reason="833s Guardian schema apply")
                        except discord.HTTPException:
                            pass

                    # per-channel overrides
                    overwrites = dict(ch.overwrites)
                    # Read-only channels
                    readonly = {
                        "announcements","changelog","community-guide","faq","server-status","resources","partners",
                        "events","support-guidelines","ticket-transcripts","staff-handbook",
                        "audit-log","message-log","join-leave-log","moderation-log","anti-raid-log","ticket-log",
                        "server-config","permission-audit",
                        "start-here","rules",
                    }
                    if ch.name in readonly and verified:
                        overwrites[verified] = _allow_readonly()
                    # Announcements: allow Admin/Community to post; members react only
                    if ch.name == "announcements":
                        if community:
                            overwrites[community] = _allow_chat()
                        for r in staff_manage:
                            overwrites[r] = _allow_chat()
                    # Support start: members can type; transcripts read-only to support/admin
                    if ch.name == "support-start" and verified:
                        overwrites[verified] = _allow_chat()
                        if support:
                            overwrites[support] = _allow_chat()
                    if ch.name == "ticket-transcripts":
                        # locked to support/admin
                        overwrites[everyone] = _deny_view()
                        if support:
                            overwrites[support] = _allow_readonly()
                        for r in staff_manage:
                            overwrites[r] = _allow_chat()
                    if ch.name in {"bot-ops","incident-room","integrations"}:
                        overwrites[everyone] = _deny_view()
                        if verified:
                            overwrites[verified] = _deny_view()
                        for r in staff_roles:
                            overwrites[r] = _allow_chat()
                    # Onboarding channel specifics
                    if cat_spec.name == "ONBOARDING":
                        if ch.name in {"verify","help-verification"} and quarantine:
                            overwrites[quarantine] = _allow_chat()
                        if ch.name in {"verify"} and verified:
                            overwrites[verified] = _deny_view()
                    # Level lounges: gate by level
                    if ch.name == "contributors-lounge" and lvl10:
                        overwrites[verified] = _deny_view() if verified else overwrites.get(everyone, _deny_view())
                        overwrites[lvl10] = _allow_chat()
                        if lvl20: overwrites[lvl20] = _allow_chat()
                        if lvl35: overwrites[lvl35] = _allow_chat()
                        if lvl50: overwrites[lvl50] = _allow_chat()
                    if ch.name == "veterans-lounge" and lvl20:
                        overwrites[verified] = _deny_view() if verified else overwrites.get(everyone, _deny_view())
                        overwrites[lvl20] = _allow_chat()
                        if lvl35: overwrites[lvl35] = _allow_chat()
                        if lvl50: overwrites[lvl50] = _allow_chat()
                    if ch.name == "elite-lounge" and lvl35:
                        overwrites[verified] = _deny_view() if verified else overwrites.get(everyone, _deny_view())
                        overwrites[lvl35] = _allow_chat()
                        if lvl50: overwrites[lvl50] = _allow_chat()
                    if ch.name == "core-feedback" and lvl50:
                        overwrites[verified] = _deny_view() if verified else overwrites.get(everyone, _deny_view())
                        overwrites[lvl50] = _allow_chat()

                    try:
                        await ch.edit(overwrites=overwrites, reason="833s Guardian schema apply")
                    except discord.HTTPException:
                        pass

                else:
                    # voice
                    vc = find_voice_channel(guild, ch_spec.name)
                    if not vc:
                        try:
                            vc = await guild.create_voice_channel(name=ch_spec.name, category=cat, reason="833s Guardian schema apply")
                        except discord.HTTPException:
                            await asyncio.sleep(0.5)
                            continue
                    else:
                        try:
                            await vc.edit(category=cat, reason="833s Guardian schema apply")
                        except discord.HTTPException:
                            pass

                await asyncio.sleep(0.2)

        # Enforce category ordering
        try:
            # Move categories in the exact order they appear
            for pos, cat_spec in enumerate(schema.categories):
                cat = find_category(guild, cat_spec.name)
                if cat:
                    await cat.edit(position=pos, reason="833s Guardian schema apply")
                    await asyncio.sleep(0.15)
        except discord.HTTPException:
            pass
