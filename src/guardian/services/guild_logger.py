from __future__ import annotations

import logging

import discord

log = logging.getLogger("guardian.guild_logger")


class GuildLogger:
    def __init__(self, bot: discord.Client) -> None:
        self._bot = bot

    async def send(self, guild: discord.Guild, channel_id: int | None, message: str) -> None:
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            await channel.send(message)
        except discord.HTTPException:
            log.exception("Failed to send guild log message")
