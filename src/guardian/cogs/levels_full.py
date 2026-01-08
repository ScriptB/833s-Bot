from __future__ import annotations

import json
import random
import time
import discord
from discord import app_commands
from discord.ext import commands

from ..services.levels_config_store import LevelsConfig
from ..services.levels_store import LevelsStore


class LevelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self._cooldowns: dict[tuple[int, int], float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        content = (message.content or "").strip()
        if len(content) < 5:
            return

        cfg = await self.bot.levels_config_store.get(message.guild.id)  # type: ignore[attr-defined]
        if not cfg.enabled:
            return

        try:
            ignored = set(json.loads(cfg.ignore_channels_json or "[]"))
        except Exception:
            ignored = set()
        if message.channel.id in ignored:
            return

        key = (message.guild.id, message.author.id)
        now = time.time()
        last = self._cooldowns.get(key, 0.0)
        if now - last < max(5, cfg.cooldown_seconds):
            return
        self._cooldowns[key] = now

        earned_today = await self.bot.levels_ledger_store.get_for_today(message.guild.id, message.author.id)  # type: ignore[attr-defined]
        if earned_today >= cfg.daily_cap:
            return

        xp_gain = random.randint(cfg.xp_min, cfg.xp_max)
        xp_gain = min(xp_gain, max(0, cfg.daily_cap - earned_today))
        if xp_gain <= 0:
            return

        await self.bot.levels_ledger_store.add_for_today(message.guild.id, message.author.id, xp_gain)  # type: ignore[attr-defined]
        _xp_in_level, level, leveled = await self.bot.levels_store.add_xp(message.guild.id, message.author.id, xp_gain)  # type: ignore[attr-defined]

        if leveled:
            role_ids = await self.bot.level_rewards_store.roles_for_level(message.guild.id, level)  # type: ignore[attr-defined]
            for rid in role_ids:
                role = message.guild.get_role(rid)
                if role:
                    try:
                        await message.author.add_roles(role, reason="Level reward (833's Guardian)")
                    except discord.HTTPException:
                        pass
            if cfg.announce:
                try:
                    await message.channel.send(f"🎉 {message.author.mention} reached **level {level}**!")
                except discord.HTTPException:
                    pass

    @app_commands.command(name="rank", description="Show a member's level and XP.")
    async def rank(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        assert interaction.guild is not None
        member = member or interaction.user  # type: ignore
        total_xp, xp, level = await self.bot.levels_store.get(interaction.guild.id, member.id)  # type: ignore[attr-defined]
        needed = LevelsStore.xp_for_next(level)
        await interaction.response.send_message(
            f"⭐ **{member.display_name}**\nLevel: **{level}**\nXP: **{xp}/{needed}**\nTotal XP: **{total_xp}**",
            ephemeral=True,
        )

    @app_commands.command(name="leaderboard", description="Top level leaderboard (all-time).")
    async def leaderboard(self, interaction: discord.Interaction, limit: app_commands.Range[int, 5, 25] = 10) -> None:
        assert interaction.guild is not None
        rows = await self.bot.levels_store.leaderboard(interaction.guild.id, int(limit))  # type: ignore[attr-defined]
        if not rows:
            await interaction.response.send_message("No data yet.", ephemeral=True)
            return
        lines = []
        for i, (uid, lvl, txp) in enumerate(rows, start=1):
            m = interaction.guild.get_member(uid)
            name = m.display_name if m else str(uid)
            lines.append(f"**{i}.** {name} — L{lvl} • {txp} XP")
        await interaction.response.send_message("🏆 **Leaderboard**\n" + "\n".join(lines), ephemeral=True)

    @app_commands.command(name="leaderboard_week", description="Top XP leaderboard (last 7 days).")
    async def leaderboard_week(self, interaction: discord.Interaction, limit: app_commands.Range[int, 5, 25] = 10) -> None:
        assert interaction.guild is not None
        rows = await self.bot.levels_ledger_store.top_week(interaction.guild.id, int(limit))  # type: ignore[attr-defined]
        if not rows:
            await interaction.response.send_message("No data yet.", ephemeral=True)
            return
        lines = []
        for i, (uid, total) in enumerate(rows, start=1):
            m = interaction.guild.get_member(uid)
            name = m.display_name if m else str(uid)
            lines.append(f"**{i}.** {name} — {total} XP")
        await interaction.response.send_message("📅 **Weekly XP**\n" + "\n".join(lines), ephemeral=True)

    @app_commands.command(name="levels_settings", description="Show leveling settings for this server.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def levels_settings(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        cfg = await self.bot.levels_config_store.get(interaction.guild.id)  # type: ignore[attr-defined]
        await interaction.response.send_message(
            f"⚙️ **Levels Settings**\n"
            f"Enabled: `{cfg.enabled}`\n"
            f"Announce: `{cfg.announce}`\n"
            f"XP range: `{cfg.xp_min}-{cfg.xp_max}`\n"
            f"Cooldown: `{cfg.cooldown_seconds}s`\n"
            f"Daily cap: `{cfg.daily_cap}`\n"
            f"Ignored channels: `{cfg.ignore_channels_json}`",
            ephemeral=True,
        )

    @app_commands.command(name="levels_enable", description="Enable/disable leveling.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def levels_enable(self, interaction: discord.Interaction, enabled: bool) -> None:
        assert interaction.guild is not None
        cfg = await self.bot.levels_config_store.get(interaction.guild.id)  # type: ignore[attr-defined]
        await self.bot.levels_config_store.upsert(
            LevelsConfig(cfg.guild_id, bool(enabled), cfg.announce, cfg.xp_min, cfg.xp_max, cfg.cooldown_seconds, cfg.daily_cap, cfg.ignore_channels_json)
        )  # type: ignore[attr-defined]
        await interaction.response.send_message(f"✅ Leveling enabled = `{enabled}`", ephemeral=True)

    @app_commands.command(name="levels_set_rate", description="Set XP range and cooldown (seconds).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def levels_set_rate(
        self,
        interaction: discord.Interaction,
        xp_min: app_commands.Range[int, 1, 100],
        xp_max: app_commands.Range[int, 1, 200],
        cooldown_seconds: app_commands.Range[int, 5, 600],
    ) -> None:
        assert interaction.guild is not None
        if xp_max < xp_min:
            await interaction.response.send_message("❌ xp_max must be >= xp_min.", ephemeral=True)
            return
        cfg = await self.bot.levels_config_store.get(interaction.guild.id)  # type: ignore[attr-defined]
        await self.bot.levels_config_store.upsert(
            LevelsConfig(cfg.guild_id, cfg.enabled, cfg.announce, int(xp_min), int(xp_max), int(cooldown_seconds), cfg.daily_cap, cfg.ignore_channels_json)
        )  # type: ignore[attr-defined]
        await interaction.response.send_message("✅ XP rate updated.", ephemeral=True)

    @app_commands.command(name="levels_set_dailycap", description="Set daily XP cap per user.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def levels_set_dailycap(self, interaction: discord.Interaction, daily_cap: app_commands.Range[int, 0, 100000]) -> None:
        assert interaction.guild is not None
        cfg = await self.bot.levels_config_store.get(interaction.guild.id)  # type: ignore[attr-defined]
        await self.bot.levels_config_store.upsert(
            LevelsConfig(cfg.guild_id, cfg.enabled, cfg.announce, cfg.xp_min, cfg.xp_max, cfg.cooldown_seconds, int(daily_cap), cfg.ignore_channels_json)
        )  # type: ignore[attr-defined]
        await interaction.response.send_message("✅ Daily cap updated.", ephemeral=True)

    @app_commands.command(name="levels_set_announce", description="Toggle level-up announcements.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def levels_set_announce(self, interaction: discord.Interaction, announce: bool) -> None:
        assert interaction.guild is not None
        cfg = await self.bot.levels_config_store.get(interaction.guild.id)  # type: ignore[attr-defined]
        await self.bot.levels_config_store.upsert(
            LevelsConfig(cfg.guild_id, cfg.enabled, bool(announce), cfg.xp_min, cfg.xp_max, cfg.cooldown_seconds, cfg.daily_cap, cfg.ignore_channels_json)
        )  # type: ignore[attr-defined]
        await interaction.response.send_message(f"✅ Announce = `{announce}`", ephemeral=True)

    @app_commands.command(name="levels_ignore_channel", description="Add/remove a channel from XP gain.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def levels_ignore_channel(self, interaction: discord.Interaction, channel: discord.TextChannel, ignored: bool) -> None:
        assert interaction.guild is not None
        cfg = await self.bot.levels_config_store.get(interaction.guild.id)  # type: ignore[attr-defined]
        try:
            arr = list(set(json.loads(cfg.ignore_channels_json or "[]")))
        except Exception:
            arr = []
        if ignored and channel.id not in arr:
            arr.append(channel.id)
        if (not ignored) and channel.id in arr:
            arr.remove(channel.id)
        await self.bot.levels_config_store.upsert(
            LevelsConfig(cfg.guild_id, cfg.enabled, cfg.announce, cfg.xp_min, cfg.xp_max, cfg.cooldown_seconds, cfg.daily_cap, json.dumps(sorted(arr)))
        )  # type: ignore[attr-defined]
        await interaction.response.send_message("✅ Updated ignored channels.", ephemeral=True)

    @app_commands.command(name="levels_reward_add", description="Give a role automatically when a level is reached.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def levels_reward_add(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 500], role: discord.Role) -> None:
        assert interaction.guild is not None
        await self.bot.level_rewards_store.add(interaction.guild.id, int(level), role.id)  # type: ignore[attr-defined]
        await interaction.response.send_message(f"✅ Reward added: level {level} → {role.mention}", ephemeral=True)

    @app_commands.command(name="levels_reward_remove", description="Remove a level reward role.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def levels_reward_remove(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 500], role: discord.Role) -> None:
        assert interaction.guild is not None
        await self.bot.level_rewards_store.remove(interaction.guild.id, int(level), role.id)  # type: ignore[attr-defined]
        await interaction.response.send_message("✅ Reward removed.", ephemeral=True)

    @app_commands.command(name="levels_reward_list", description="List configured level rewards.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def levels_reward_list(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        pairs = await self.bot.level_rewards_store.list(interaction.guild.id)  # type: ignore[attr-defined]
        if not pairs:
            await interaction.response.send_message("No rewards configured.", ephemeral=True)
            return
        lines = []
        for lvl, rid in pairs:
            role = interaction.guild.get_role(rid)
            lines.append(f"Level **{lvl}** → {role.mention if role else rid}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="levels_reset_user", description="Reset a user's level data.")
    @app_commands.checks.has_permissions(administrator=True)
    async def levels_reset_user(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild is not None
        await self.bot.levels_store.reset_user(interaction.guild.id, member.id)  # type: ignore[attr-defined]
        await interaction.response.send_message("✅ User level data reset.", ephemeral=True)

    @app_commands.command(name="levels_reset_all", description="Reset all level data in this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def levels_reset_all(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await self.bot.levels_store.reset_guild(interaction.guild.id)  # type: ignore[attr-defined]
        await interaction.response.send_message("✅ All level data reset.", ephemeral=True)
