from __future__ import annotations

import discord
from discord.ext import commands

from ..services.join_velocity import JoinVelocity


class AntiRaidCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self._velocity = JoinVelocity(window_seconds=60, threshold=8)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not self._velocity.record():
            return
        guild = member.guild
        try:
            for name in ("general", "media", "help"):
                ch = discord.utils.get(guild.text_channels, name=name)
                if isinstance(ch, discord.TextChannel):
                    ow = ch.overwrites_for(guild.default_role)
                    ow.send_messages = False
                    await ch.set_permissions(guild.default_role, overwrite=ow, reason="Anti-raid lockdown")
        except Exception:
            pass
        alert = discord.utils.get(guild.text_channels, name="guardian-failsafe") or discord.utils.get(guild.text_channels, name="mod-logs")
        if alert:
            try:
                await alert.send("⚠️ Anti-raid triggered: join velocity exceeded. Soft-lockdown applied.")
            except discord.HTTPException:
                pass
