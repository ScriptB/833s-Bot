from __future__ import annotations

import asyncio
from typing import Iterable

import discord
from discord import app_commands
from discord.ext import commands


def _p(*, view: bool, send: bool, history: bool = True, reactions: bool = True, threads: bool = True) -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=view,
        send_messages=send,
        read_message_history=history,
        add_reactions=reactions,
        create_public_threads=threads,
        create_private_threads=threads,
        send_messages_in_threads=send,
    )


def _safe_embed(title: str, description: str) -> discord.Embed:
    # hard limit safety
    if len(description) > 4000:
        description = description[:3990] + "…"
    return discord.Embed(title=title, description=description)


class SetupAutoConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="guardian_overhaul",
        description="Complete server-wide teardown and professional rebuild for 833s.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def guardian_overhaul(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        guild = interaction.guild

        await interaction.response.defer(ephemeral=True, thinking=True)

        bot_member = guild.me or guild.get_member(self.bot.user.id)  # type: ignore[attr-defined]
        if not bot_member:
            await interaction.followup.send("❌ Bot member not found.", ephemeral=True)
            return

        gperms = bot_member.guild_permissions
        if not (gperms.manage_channels and gperms.manage_roles):
            await interaction.followup.send("❌ Missing permissions: Manage Channels + Manage Roles.", ephemeral=True)
            return

        report: list[str] = []

        async def paced() -> None:
            await asyncio.sleep(0.35)

        # --- Server settings (defensive: only use fields guaranteed in discord.py) ---
        try:
            await guild.edit(
                name="833s",
                verification_level=discord.VerificationLevel.high,
                default_notifications=discord.NotificationLevel.only_mentions,
                explicit_content_filter=discord.ContentFilter.all_members,
                reason="833s Guardian overhaul",
            )
            report.append("✅ Server settings hardened.")
        except Exception:
            report.append("⚠️ Server settings not fully updated.")
        await paced()

        # --- Roles ---
        def perms(**kwargs) -> discord.Permissions:
            return discord.Permissions(**kwargs)

        async def ensure_role(
            name: str,
            *,
            color: discord.Color | None = None,
            permissions: discord.Permissions | None = None,
            hoist: bool = False,
            mentionable: bool = False,
        ) -> discord.Role | None:
            existing = discord.utils.get(guild.roles, name=name)
            if existing:
                return existing
            try:
                r = await guild.create_role(
                    name=name,
                    colour=color or discord.Color.default(),
                    permissions=permissions or discord.Permissions.none(),
                    hoist=hoist,
                    mentionable=mentionable,
                    reason="833s Guardian overhaul",
                )
                report.append(f"✅ Role created: {name}")
                return r
            except Exception:
                report.append(f"⚠️ Role create failed: {name}")
                return None

        role_admin = await ensure_role("Admin", color=discord.Color.red(), permissions=perms(administrator=True), hoist=True)
        await paced()
        role_mod = await ensure_role(
            "Moderator",
            color=discord.Color.orange(),
            permissions=perms(
                moderate_members=True,
                manage_messages=True,
                manage_threads=True,
                kick_members=True,
                ban_members=True,
                view_audit_log=True,
            ),
            hoist=True,
        )
        await paced()
        role_helper = await ensure_role(
            "Helper",
            color=discord.Color.gold(),
            permissions=perms(moderate_members=True, manage_messages=True),
            hoist=True,
        )
        await paced()

        # Access roles
        role_verified = await ensure_role("Verified", color=discord.Color.green())
        await paced()
        role_member = await ensure_role("Member", color=discord.Color.dark_green())
        await paced()
        role_muted = await ensure_role("Muted", color=discord.Color.dark_grey())
        await paced()

        # Level roles
        level_map: list[tuple[int, str]] = [(5, "Bronze"), (10, "Silver"), (20, "Gold"), (35, "Platinum"), (50, "Diamond")]
        level_roles: list[tuple[int, discord.Role]] = []
        for lvl, name in level_map:
            r = await ensure_role(f"Level {lvl} • {name}", color=discord.Color.blurple())
            await paced()
            if r:
                level_roles.append((lvl, r))

        # Interests (for RR panel)
        interest_names = ["Gamer", "Developer", "Artist", "Music"]
        interest_roles: list[discord.Role] = []
        for nm in interest_names:
            r = await ensure_role(nm)
            await paced()
            if r:
                interest_roles.append(r)

        # --- Role hierarchy (best effort under bot's top role) ---
        try:
            top_pos = bot_member.top_role.position
            desired: list[discord.Role] = []
            for r in [role_admin, role_mod, role_helper, role_verified]:
                if r:
                    desired.append(r)
            for _, r in sorted(level_roles, key=lambda x: x[0], reverse=True):
                desired.append(r)
            desired.extend(interest_roles)
            if role_member:
                desired.append(role_member)
            if role_muted:
                desired.append(role_muted)

            movable = [r for r in desired if r.position < top_pos]
            positions = {}
            pos = top_pos - 1
            for r in movable:
                positions[r] = pos
                pos -= 1
            if positions:
                await guild.edit_role_positions(positions=positions, reason="833s Guardian overhaul hierarchy")
                report.append("✅ Role hierarchy adjusted.")
        except Exception:
            report.append("⚠️ Role hierarchy not adjusted.")
        await paced()

        # --- Categories / Channels ---
        async def ensure_category(name: str) -> discord.CategoryChannel | None:
            c = discord.utils.get(guild.categories, name=name)
            if c:
                return c
            try:
                c = await guild.create_category(name=name, reason="833s Guardian overhaul")
                report.append(f"✅ Category created: {name}")
                return c
            except Exception:
                report.append(f"⚠️ Category failed: {name}")
                return None

        async def ensure_text(
            category: discord.CategoryChannel | None,
            name: str,
            overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite],
            topic: str | None = None,
            slowmode: int = 0,
        ) -> discord.TextChannel | None:
            existing = discord.utils.get(guild.text_channels, name=name)
            if existing:
                # Update overwrites (best effort)
                try:
                    await existing.edit(category=category, overwrites=overwrites, topic=topic, slowmode_delay=slowmode, reason="833s Guardian overhaul")
                except Exception:
                    pass
                return existing
            try:
                ch = await guild.create_text_channel(
                    name=name,
                    category=category,
                    overwrites=overwrites,
                    topic=topic,
                    slowmode_delay=slowmode,
                    reason="833s Guardian overhaul",
                )
                report.append(f"✅ Channel created: #{name}")
                return ch
            except Exception:
                report.append(f"⚠️ Channel failed: #{name}")
                return None

        # Overwrite templates
        everyone = guild.default_role
        staff_roles: list[discord.Role] = [r for r in [role_admin, role_mod, role_helper] if r]
        verified_roles: list[discord.Role] = [r for r in [role_verified, role_member] if r]

        # Onboarding channels: visible to everyone; write restricted as needed
        cat_start = await ensure_category("👋 Start Here")
        await paced()
        cat_comm = await ensure_category("💬 Community")
        await paced()
        cat_support = await ensure_category("🆘 Support")
        await paced()
        cat_staff = await ensure_category("🛡️ Staff")
        await paced()

        ow_readonly = {everyone: _p(view=True, send=False)}
        for r in staff_roles:
            ow_readonly[r] = _p(view=True, send=True)

        ow_verify = {everyone: _p(view=True, send=True)}
        if role_muted:
            ow_verify[role_muted] = _p(view=True, send=False, reactions=False)

        # Main chat should be gated to Verified+
        ow_gated = {everyone: _p(view=True, send=False)}
        if role_verified:
            ow_gated[role_verified] = _p(view=True, send=True)
        if role_member:
            ow_gated[role_member] = _p(view=True, send=True)
        if role_muted:
            ow_gated[role_muted] = _p(view=True, send=False, reactions=False)
        for r in staff_roles:
            ow_gated[r] = _p(view=True, send=True)

        ow_staff = {everyone: _p(view=False, send=False)}
        for r in staff_roles:
            ow_staff[r] = _p(view=True, send=True)

        ch_rules = await ensure_text(cat_start, "rules", overwrites=ow_readonly, topic="Rules and conduct")
        await paced()
        ch_verify = await ensure_text(cat_start, "verify", overwrites=ow_verify, topic="Verification", slowmode=2)
        await paced()
        ch_intro = await ensure_text(cat_start, "introductions", overwrites=ow_gated, topic="Introduce yourself", slowmode=5)
        await paced()

        ch_general = await ensure_text(cat_comm, "general", overwrites=ow_gated, topic="General chat")
        await paced()
        ch_media = await ensure_text(cat_comm, "media", overwrites=ow_gated, topic="Images and clips", slowmode=2)
        await paced()
        ch_bot = await ensure_text(cat_comm, "bot-commands", overwrites=ow_gated, topic="Bot commands", slowmode=2)
        await paced()

        ch_help = await ensure_text(cat_support, "help", overwrites=ow_gated, topic="Ask for help", slowmode=2)
        await paced()

        ch_staff = await ensure_text(cat_staff, "staff-chat", overwrites=ow_staff, topic="Staff coordination")
        await paced()
        ch_modlogs = await ensure_text(cat_staff, "mod-logs", overwrites={**ow_staff, **{r: _p(view=True, send=False) for r in staff_roles}}, topic="Logs (manual)")
        await paced()

        # --- Blog posts (best-effort: don't spam if already posted by bot) ---
        async def ensure_blog(ch: discord.TextChannel | None, key: str, embed: discord.Embed) -> None:
            if not ch:
                return
            try:
                async for m in ch.history(limit=20):
                    if m.author.id == self.bot.user.id and m.embeds:
                        if m.embeds[0].title == embed.title:
                            return
            except Exception:
                # history might fail if missing perms
                pass
            try:
                await ch.send(embed=embed)
            except Exception:
                pass

        await ensure_blog(
            ch_rules,
            "rules",
            _safe_embed(
                "Welcome to 833s",
                "This server is professionally moderated.\n\n"
                "Rules:\n"
                "1) Respect everyone\n"
                "2) No spam, scams, or harassment\n"
                "3) Follow Discord ToS\n"
                "4) Keep content appropriate\n"
                "5) Staff decisions are final\n",
            ),
        )
        await paced()

        await ensure_blog(
            ch_verify,
            "verify",
            _safe_embed(
                "Verification",
                "Type **I agree** in this channel to get access.\n\n"
                "If you have issues, post in **#help** after verifying.",
            ),
        )
        await paced()

        await ensure_blog(
            ch_intro,
            "introductions",
            _safe_embed(
                "Introductions",
                "Template:\n"
                "• Name / Nickname\n"
                "• Interests\n"
                "• Timezone\n"
                "• What you want from 833s\n",
            ),
        )
        await paced()

        await ensure_blog(
            ch_help,
            "help",
            _safe_embed(
                "Help Guidelines",
                "Include:\n"
                "• What you're trying to do\n"
                "• What you tried\n"
                "• Exact error messages / screenshots\n\n"
                "Be patient; staff are volunteers.",
            ),
        )
        await paced()

        # --- Bot systems (levels / starboard / RR / server config) ---
        try:
            cfg = await self.bot.levels_config_store.get(guild.id)  # type: ignore[attr-defined]
            await self.bot.levels_config_store.upsert(  # type: ignore[attr-defined]
                type(cfg)(
                    guild_id=guild.id,
                    enabled=True,
                    announce=True,
                    xp_min=cfg.xp_min,
                    xp_max=cfg.xp_max,
                    cooldown_seconds=cfg.cooldown_seconds,
                    daily_cap=cfg.daily_cap,
                    ignore_channels_json=cfg.ignore_channels_json,
                )
            )
            for lvl, r in level_roles:
                await self.bot.level_rewards_store.add(guild.id, int(lvl), r.id)  # type: ignore[attr-defined]
            report.append("✅ Level system enabled + rewards synced.")
        except Exception:
            report.append("⚠️ Level system sync failed.")
        await paced()

        try:
            target = ch_media or ch_general
            if target:
                await self.bot.starboard_store.set_config(guild.id, target.id, 3)  # type: ignore[attr-defined]
                report.append(f"✅ Starboard set: #{target.name} (⭐ x3).")
        except Exception:
            report.append("⚠️ Starboard config failed.")
        await paced()

        # Reaction roles panel in #bot-commands or #rules? Use #bot-commands for safety; #rules is read-only.
        try:
            if ch_bot and interest_roles:
                # Optional UI helper. If unavailable, skip the interactive view.
                ReactionRoleView = None
                try:
                    from ..ui.reaction_roles import ReactionRoleView  # type: ignore
                except Exception:
                    ReactionRoleView = None

                embed = _safe_embed("Self Roles", "Pick your interests. You can change these any time.")
                panel_msg = await ch_bot.send(embed=embed)

                await self.bot.rr_store.create_panel(guild.id, ch_bot.id, panel_msg.id, "Self Roles", "Pick your interests.", max_values=min(4, len(interest_roles)))  # type: ignore[attr-defined]
                for r in interest_roles:
                    await self.bot.rr_store.add_option(guild.id, panel_msg.id, r.id, r.name, None)  # type: ignore[attr-defined]

                data = await self.bot.rr_store.get_panel(guild.id, panel_msg.id)  # type: ignore[attr-defined]
                panel, options = data
                if ReactionRoleView is None:
                    raise RuntimeError("ReactionRoleView unavailable")
                view = ReactionRoleView(
                    guild.id,
                    panel_msg.id,
                    [(int(rid), str(lbl), (str(e) if e else None)) for (rid, lbl, e) in options],
                    int(panel[3]),
                )
                self.bot.add_view(view, message_id=panel_msg.id)  # type: ignore[attr-defined]
                await panel_msg.edit(view=view)
                report.append("✅ Self-role panel posted in #bot-commands.")
        except Exception:
            report.append("⚠️ Self-role panel failed.")
        await paced()

        try:
            if hasattr(self.bot, "server_config_store"):
                s = await self.bot.server_config_store.get(guild.id)  # type: ignore[attr-defined]
                autorole_id = role_verified.id if role_verified else None
                await self.bot.server_config_store.upsert(  # type: ignore[attr-defined]
                    type(s)(
                        guild.id,
                        (ch_general.id if ch_general else None),
                        True,
                        autorole_id,
                        (ch_bot.id if ch_bot else None),
                    )
                )
                report.append("✅ Welcome + autorole set (Verified).")
        except Exception:
            report.append("⚠️ Welcome/autorole config failed.")
        await paced()

        # --- Verification handler: add a lightweight listener in this cog? ---
        # Not implemented here; relies on existing welcome cog for autorole on join.
        # We keep copy-only instructions in #verify.

        await interaction.followup.send("\n".join(report[:35]), ephemeral=True)
