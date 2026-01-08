from __future__ import annotations

import random
import time
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands


@dataclass
class _GuildCounters:
    day_key: str
    sent_today: int


class AmbientCog(commands.Cog):
    """Non-moderation ambient community behavior.

    - Optional lightweight replies in configured channels
    - Optional opt-in pings (mentions) with strict cooldowns

    Notes
    - Message content intent is NOT required for this cog to function, but if message content intent is disabled,
      Discord may deliver limited message content for non-mentioned messages depending on the app's configuration.
      This cog therefore never depends on parsing message text; it reacts probabilistically.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self._last_channel_sent: dict[int, float] = {}
        self._last_user_ping: dict[int, float] = {}
        self._guild_counters: dict[int, _GuildCounters] = {}

        self._lines: list[str] = [
            "Drop a quick update: what are you doing right now?",
            "One small win from today?",
            "Recommend something: game, song, video, or tool.",
            "If you could add one feature to the server, what is it?",
            "What should the next community prompt be?",
        ]

    def _day_key(self) -> str:
        return time.strftime("%Y%m%d", time.gmtime())

    async def _channel_allowed(self, guild_id: int, channel_id: int) -> bool:
        mode = getattr(self.bot.settings, "ambient_channel_mode", "bot_commands_only")  # type: ignore[attr-defined]
        if mode == "all":
            return True

        cfg = await self.bot.server_config_store.get(guild_id)  # type: ignore[attr-defined]
        if mode == "bot_commands_only":
            return bool(cfg.bot_commands_channel_id) and int(cfg.bot_commands_channel_id) == int(channel_id)

        # "allowlist" mode: not yet configurable in DB; treat as bot_commands_only.
        return bool(cfg.bot_commands_channel_id) and int(cfg.bot_commands_channel_id) == int(channel_id)

    def _within_channel_cooldown(self, channel_id: int) -> bool:
        cd = int(getattr(self.bot.settings, "ambient_per_channel_cooldown_seconds", 600))  # type: ignore[attr-defined]
        last = self._last_channel_sent.get(int(channel_id), 0.0)
        return (time.time() - last) < cd

    def _guild_cap_reached(self, guild_id: int) -> bool:
        cap = int(getattr(self.bot.settings, "ambient_daily_guild_cap", 30))  # type: ignore[attr-defined]
        key = self._day_key()
        cur = self._guild_counters.get(int(guild_id))
        if cur is None or cur.day_key != key:
            self._guild_counters[int(guild_id)] = _GuildCounters(day_key=key, sent_today=0)
            return False
        return cur.sent_today >= cap

    def _bump_guild_count(self, guild_id: int) -> None:
        key = self._day_key()
        cur = self._guild_counters.get(int(guild_id))
        if cur is None or cur.day_key != key:
            cur = _GuildCounters(day_key=key, sent_today=0)
            self._guild_counters[int(guild_id)] = cur
        cur.sent_today += 1

    def _roll_reply(self) -> bool:
        chance = int(getattr(self.bot.settings, "ambient_reply_chance_percent", 2))  # type: ignore[attr-defined]
        chance = max(0, min(100, chance))
        return random.randint(1, 100) <= chance

    async def _member_level(self, guild_id: int, user_id: int) -> int:
        _, _, lvl = await self.bot.levels_store.get(guild_id, user_id)  # type: ignore[attr-defined]
        return int(lvl)

    def _within_user_ping_cooldown(self, user_id: int) -> bool:
        cd = int(getattr(self.bot.settings, "ambient_per_user_ping_cooldown_seconds", 21600))  # type: ignore[attr-defined]
        last = self._last_user_ping.get(int(user_id), 0.0)
        return (time.time() - last) < cd

    async def _maybe_ping_author(self, msg: discord.Message) -> str:
        if not getattr(self.bot.settings, "ambient_pings_enabled", False):  # type: ignore[attr-defined]
            return ""
        if not isinstance(msg.author, discord.Member) or msg.guild is None:
            return ""
        if msg.author.bot:
            return ""
        if self._within_user_ping_cooldown(msg.author.id):
            return ""
        min_lvl = int(getattr(self.bot.settings, "ambient_min_level_for_pings", 5))  # type: ignore[attr-defined]
        lvl = await self._member_level(msg.guild.id, msg.author.id)
        if lvl < min_lvl:
            return ""
        opted = await self.bot.ambient_store.get_pings_opt_in(msg.guild.id, msg.author.id)  # type: ignore[attr-defined]
        if not opted:
            return ""
        self._last_user_ping[int(msg.author.id)] = time.time()
        return msg.author.mention

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message) -> None:
        if not getattr(self.bot.settings, "ambient_enabled", False):  # type: ignore[attr-defined]
            return
        if message.guild is None:
            return
        if message.author.bot:
            return
        if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return

        if not await self._channel_allowed(message.guild.id, message.channel.id):
            return
        if self._within_channel_cooldown(message.channel.id):
            return
        if self._guild_cap_reached(message.guild.id):
            return
        if not self._roll_reply():
            return

        mention = await self._maybe_ping_author(message)
        content = random.choice(self._lines)
        if mention:
            content = f"{mention} {content}"

        try:
            await message.channel.send(content, allowed_mentions=discord.AllowedMentions(users=bool(mention), roles=False, everyone=False))
            self._last_channel_sent[int(message.channel.id)] = time.time()
            self._bump_guild_count(message.guild.id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return

    @app_commands.guild_only()
    @app_commands.command(name="ambient_optin", description="Opt in/out of occasional ambient pings (mentions).")
    async def ambient_optin(self, interaction: discord.Interaction, enabled: bool) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return
        await self.bot.ambient_store.set_pings_opt_in(interaction.guild.id, interaction.user.id, bool(enabled))  # type: ignore[attr-defined]
        await interaction.response.send_message("Updated.", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.command(name="ambient_status", description="Show ambient system status for this server.")
    async def ambient_status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return
        cfg = await self.bot.server_config_store.get(interaction.guild.id)  # type: ignore[attr-defined]
        key = self._day_key()
        cur = self._guild_counters.get(int(interaction.guild.id))
        sent_today = 0 if (cur is None or cur.day_key != key) else cur.sent_today
        await interaction.response.send_message(
            f"enabled={bool(self.bot.settings.ambient_enabled)} pings_enabled={bool(self.bot.settings.ambient_pings_enabled)} "
            f"channel_mode={self.bot.settings.ambient_channel_mode} bot_commands_channel_id={cfg.bot_commands_channel_id} "
            f"sent_today={sent_today}/{int(self.bot.settings.ambient_daily_guild_cap)}",
            ephemeral=True,
        )
