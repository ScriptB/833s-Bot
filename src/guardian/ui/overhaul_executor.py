from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import discord
from discord.ext import commands

from ..services.discord_safety import safe_followup

# --- Constants -------------------------------------------------

MAX_RETRIES = 3
RETRY_DELAY = 1.0


class OverhaulExecutor:
    """Executes the full server overhaul based on a config dict."""

    def __init__(self, cog: commands.Cog, guild: discord.Guild, config: dict[str, Any]) -> None:
        self.cog = cog
        self.bot = cog.bot
        self.guild = guild
        self.config = config
        self.report: list[str] = []

    async def run(self) -> str:
        """Run the full overhaul and return a summary string."""
        start = time.time()
        self.report.append("🛠️ Starting server overhaul...")
        try:
            await self._apply_server_settings()
            await self._nuke_all()
            await self._create_roles()
            await self._set_role_hierarchy()
            await self._create_categories_and_channels()
            await self._setup_reaction_roles()
            await self._configure_bot_modules()
            elapsed = f"{time.time() - start:.2f}s"
            self.report.append(f"\n🎉 Overhaul completed in {elapsed}.")
            return "\n".join(self.report)
        except Exception as e:
            self.report.append(f"\n❌ Overhaul failed: {type(e).__name__}: {e}")
            return "\n".join(self.report)

    # -------------------------------------------------------------------------

    async def _apply_server_settings(self) -> None:
        for attempt in range(MAX_RETRIES):
            try:
                await self.guild.edit(
                    name=self.config["server_name"],
                    verification_level=getattr(discord.VerificationLevel, self.config["verification_level"], discord.VerificationLevel.high),
                    default_notifications=getattr(discord.NotificationLevel, self.config["default_notifications"], discord.NotificationLevel.only_mentions),
                    explicit_content_filter=getattr(discord.ContentFilter, self.config["content_filter"], discord.ContentFilter.all_members),
                    reason="833s Guardian Overhaul",
                )
                self.report.append("✅ Server settings applied.")
                return
            except discord.HTTPException as e:
                if attempt == MAX_RETRIES - 1:
                    self.report.append(f"⚠️ Server settings failed after {MAX_RETRIES} attempts: {e}")
                    return
                self.report.append(f"⚠️ Server settings failed (attempt {attempt + 1}), retrying...")
                await asyncio.sleep(RETRY_DELAY)

    async def _nuke_all(self) -> None:
        """Delete ALL channels and ALL roles (except @everyone and managed/bot top roles)."""
        bot_member = self.guild.me or self.guild.get_member(self.bot.user.id)
        if not bot_member:
            raise RuntimeError("Bot member not found.")
        top_pos = bot_member.top_role.position

        # Delete all channels
        channel_count = 0
        for ch in list(self.guild.channels):
            try:
                await ch.delete(reason="833s Guardian Overhaul: nuke")
                channel_count += 1
                await asyncio.sleep(0.2)  # avoid rate limit
            except discord.HTTPException as e:
                self.report.append(f"⚠️ Failed to delete channel {ch.name}: {e}")
        self.report.append(f"✅ Deleted {channel_count} channels.")

        # Delete all roles (skip @everyone, managed, and any role >= bot's top role)
        role_count = 0
        for role in sorted(self.guild.roles, key=lambda r: r.position, reverse=True):
            if role.is_default() or role.managed or role.position >= top_pos:
                continue
            try:
                await role.delete(reason="833s Guardian Overhaul: nuke")
                role_count += 1
                await asyncio.sleep(0.2)
            except discord.HTTPException as e:
                self.report.append(f"⚠️ Failed to delete role {role.name}: {e}")
        self.report.append(f"✅ Deleted {role_count} roles.")

    async def _create_roles(self) -> dict[str, discord.Role]:
        """Create all roles from config and return a name->role map."""
        role_map: dict[str, discord.Role] = {}
        for r_cfg in self.config["roles"]:
            for attempt in range(MAX_RETRIES):
                try:
                    color_obj = getattr(discord.Color, r_cfg["color"], discord.Color.default)()
                    role = await self.guild.create_role(
                        name=r_cfg["name"],
                        color=color_obj,
                        hoist=r_cfg["hoist"],
                        mentionable=r_cfg["mentionable"],
                        reason="833s Guardian Overhaul",
                    )
                    role_map[r_cfg["name"]] = role
                    await asyncio.sleep(0.2)
                    break
                except discord.HTTPException as e:
                    if attempt == MAX_RETRIES - 1:
                        self.report.append(f"⚠️ Failed to create role '{r_cfg['name']}' after {MAX_RETRIES} attempts: {e}")
                        break
                    self.report.append(f"⚠️ Role '{r_cfg['name']}' creation failed (attempt {attempt + 1}), retrying...")
                    await asyncio.sleep(RETRY_DELAY)
        self.report.append(f"✅ Created {len(role_map)} roles.")
        return role_map

    async def _set_role_hierarchy(self) -> None:
        """Arrange role hierarchy: higher-level roles above lower-level ones."""
        bot_member = self.guild.me or self.guild.get_member(self.bot.user.id)
        if not bot_member:
            return
        top_pos = bot_member.top_role.position

        # Desired order: Diamond > Platinum > Gold > Silver > Bronze > Member > Verified > ping roles > Muted
        order = [
            "Diamond", "Platinum", "Gold", "Silver", "Bronze",
            "Member", "Verified",
            "Pet Pings", "Announce Pings", "Giveaway Pings", "Event Pings",
            "Muted",
        ]
        positions = {}
        pos = top_pos - 1
        for name in order:
            role = discord.utils.get(self.guild.roles, name=name)
            if role and role.position < top_pos:
                positions[role] = pos
                pos -= 1
        if positions:
            await self.guild.edit_role_positions(positions=positions, reason="833s Guardian Overhaul")
            self.report.append("✅ Set role hierarchy.")
        else:
            self.report.append("⚠️ No roles to arrange.")

    async def _create_categories_and_channels(self) -> None:
        """Create categories and channels with per-role permissions."""
        everyone = self.guild.default_role
        role_map = {r.name: r for r in self.guild.roles}
        # Helper perms
        def perms(view: bool, send: bool, history: bool = True, reactions: bool = True, threads: bool = True) -> discord.PermissionOverwrite:
            return discord.PermissionOverwrite(
                view_channel=view,
                send_messages=send,
                read_message_history=history,
                add_reactions=reactions,
                create_public_threads=threads,
                create_private_threads=threads,
                send_messages_in_threads=send,
            )
        # Overwrites
        ow_verified = {everyone: perms(view=True, send=False)}
        if "Verified" in role_map:
            ow_verified[role_map["Verified"]] = perms(view=True, send=True)
        if "Member" in role_map:
            ow_verified[role_map["Member"]] = perms(view=True, send=True)
        if "Muted" in role_map:
            ow_verified[role_map["Muted"]] = perms(view=True, send=False, reactions=False)
        # Staff-only (no admin/staff roles per request, but keep hidden)
        ow_staff = {everyone: perms(view=False, send=False)}
        # Ping roles get same access as members
        for ping in ("Pet Pings", "Announce Pings", "Giveaway Pings", "Event Pings"):
            if ping in role_map:
                ow_verified[role_map[ping]] = perms(view=True, send=True)

        # Create categories and channels
        for cat_cfg in self.config["categories"]:
            try:
                category = await self.guild.create_category(cat_cfg["name"], reason="833s Guardian Overhaul")
                await asyncio.sleep(0.2)
                for ch_name in cat_cfg["channels"]:
                    # Determine overwrites
                    if cat_cfg["name"] == "👋 Start Here":
                        overwrites = ow_verified
                    elif cat_cfg["name"] == "💬 Community":
                        overwrites = ow_verified
                    elif cat_cfg["name"] == "🆘 Support":
                        overwrites = ow_verified
                    elif cat_cfg["name"] == "🎉 Events":
                        overwrites = ow_verified
                    elif cat_cfg["name"] == "🛡️ Staff":
                        overwrites = ow_staff
                    else:
                        overwrites = ow_verified
                    await self.guild.create_text_channel(ch_name, category=category, overwrites=overwrites, reason="833s Guardian Overhaul")
                    await asyncio.sleep(0.2)
            except Exception as e:
                self.report.append(f"⚠️ Failed to create category '{cat_cfg['name']}': {e}")
        self.report.append("✅ Created categories and channels.")

    async def _setup_reaction_roles(self) -> None:
        """Create the reaction-roles channel and post the UI."""
        channel_name = self.config["reaction_roles_channel"]
        category = discord.utils.get(self.guild.categories, name="💬 Community")
        try:
            channel = await self.guild.create_text_channel(channel_name, category=category, reason="833s Guardian Overhaul")
        except discord.HTTPException as e:
            self.report.append(f"⚠️ Failed to create reaction-roles channel: {e}")
            return

        # Build UI
        from .overhaul_setup import OverhaulSetupView
        view = ReactionRolesView(self.guild, self.config)
        embed = discord.Embed(
            title=self.config["reaction_roles_message_title"],
            description=self.config["reaction_roles_message_description"],
        )
        for role_name in ("Pet Pings", "Announce Pings", "Giveaway Pings", "Event Pings"):
            role = discord.utils.get(self.guild.roles, name=role_name)
            if role:
                embed.add_field(name=role_name, value=f"Click the button to get {role.mention}.", inline=False)
        try:
            msg = await channel.send(embed=embed, view=view)
        except discord.HTTPException as e:
            self.report.append(f"⚠️ Failed to post reaction roles panel: {e}")
            return

        # Store in DB for persistence
        try:
            await self.bot.rr_store.create(self.guild.id, channel.id, msg.id, embed.title, embed.description, max_values=1)  # type: ignore[attr-defined]
            for role_name in ("Pet Pings", "Announce Pings", "Giveaway Pings", "Event Pings"):
                role = discord.utils.get(self.guild.roles, name=role_name)
                if role:
                    await self.bot.rr_store.add_option(self.guild.id, msg.id, role.id, role_name, None)  # type: ignore[attr-defined]
            # Re-attach persistent view
            self.bot.add_view(view, message_id=msg.id)  # type: ignore[attr-defined]
            self.report.append("✅ Reaction roles panel created and persisted.")
        except Exception as e:
            self.report.append(f"⚠️ Failed to store reaction roles panel: {e}")

    async def _configure_bot_modules(self) -> None:
        """Configure levels, starboard, and other bot modules."""
        # Enable levels and sync level rewards
        try:
            cfg = await self.bot.levels_config_store.get(self.guild.id)  # type: ignore[attr-defined]
            await self.bot.levels_config_store.upsert(  # type: ignore[attr-defined]
                type(cfg)(
                    guild_id=self.guild.id,
                    enabled=True,
                    announce=True,
                    xp_min=cfg.xp_min,
                    xp_max=cfg.xp_max,
                    cooldown_seconds=cfg.cooldown_seconds,
                    daily_cap=cfg.daily_cap,
                    ignore_channels_json=cfg.ignore_channels_json,
                )
            )
            level_map = {"Bronze": 5, "Silver": 10, "Gold": 20, "Platinum": 35, "Diamond": 50}
            rewards_added = 0
            for name, lvl in level_map.items():
                role = discord.utils.get(self.guild.roles, name=name)
                if role:
                    await self.bot.level_rewards_store.add(self.guild.id, lvl, role.id)  # type: ignore[attr-defined]
                    rewards_added += 1
            self.report.append(f"✅ Levels enabled and {rewards_added} level rewards synced.")
        except Exception as e:
            self.report.append(f"⚠️ Levels setup failed: {e}")

        # Set starboard to #media (or #general if missing)
        try:
            target = discord.utils.get(self.guild.text_channels, name="media") or discord.utils.get(self.guild.text_channels, name="general")
            if target:
                await self.bot.starboard_store.set_config(self.guild.id, target.id, 3)  # type: ignore[attr-defined]
                self.report.append(f"✅ Starboard set to #{target.name}.")
        except Exception as e:
            self.report.append(f"⚠️ Starboard setup failed: {e}")

        # Set welcome/autorole/log channels if they exist
        try:
            welcome_ch = discord.utils.get(self.guild.text_channels, name="general")
            autorole = discord.utils.get(self.guild.roles, name="Verified")
            log_ch = discord.utils.get(self.guild.text_channels, name="mod-logs")
            if welcome_ch or autorole or log_ch:
                cfg = await self.bot.guild_store.get(self.guild.id)  # type: ignore[attr-defined]
                await self.bot.guild_store.upsert(  # type: ignore[attr-defined]
                    type(cfg)(
                        guild_id=self.guild.id,
                        welcome_channel_id=welcome_ch.id if welcome_ch else cfg.welcome_channel_id,
                        autorole_id=autorole.id if autorole else cfg.autorole_id,
                        log_channel_id=log_ch.id if log_ch else cfg.log_channel_id,
                        anti_spam_max_msgs=cfg.anti_spam_max_msgs,
                        anti_spam_window_seconds=cfg.anti_spam_window_seconds,
                        anti_spam_timeout_seconds=cfg.anti_spam_timeout_seconds,
                    )
                )
                self.report.append("✅ Welcome/autorole/log channels configured.")
        except Exception as e:
            self.report.append(f"⚠️ Welcome/autorole/log config failed: {e}")


# --- Reaction Roles UI -------------------------------------------------------

class ReactionRolesView(discord.ui.View):
    """Persistent view for reaction-roles panel."""

    def __init__(self, guild: discord.Guild, config: dict[str, Any]) -> None:
        super().__init__(timeout=None)  # persistent
        self.guild = guild
        self.config = config
        # Add buttons for each ping role
        for role_name in ("Pet Pings", "Announce Pings", "Giveaway Pings", "Event Pings"):
            btn = discord.ui.Button(label=role_name, style=discord.ButtonStyle.secondary)
            btn.callback = self._make_callback(role_name)
            self.add_item(btn)

    def _make_callback(self, role_name: str):
        async def callback(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True, thinking=True)
            role = discord.utils.get(self.guild.roles, name=role_name)
            if not role:
                await interaction.followup.send("Role not found.", ephemeral=True)
                return
            member = interaction.user
            if role in member.roles:
                await member.remove_roles(role, reason="Reaction role removal")
                await interaction.followup.send(f"Removed {role_name}.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Reaction role assignment")
                await interaction.followup.send(f"Added {role_name}.", ephemeral=True)
        return callback
