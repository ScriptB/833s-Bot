from __future__ import annotations

import asyncio
import discord

from ..lookup import find_text_channel


class ChannelBootstrapper:
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot

    async def ensure_first_posts(self, guild: discord.Guild) -> None:
        # Match your current template.
        targets = {
            "rules": self._rules_text(),
            "welcome": self._welcome_text(),
            "introductions": self._introductions_text(),
            "tickets": self._tickets_text(),
            "server-info": self._server_info_text(),
        }
        for name, body in targets.items():
            ch = find_text_channel(guild, name)
            if not isinstance(ch, discord.TextChannel):
                continue
            try:
                # Check for existing bootstrap posts (without marker)
                already = False
                async for m in ch.history(limit=15, oldest_first=True):
                    if m.author == guild.me and m.content and any(
                        text in m.content
                        for text in [
                            "Server Rules",
                            "Welcome to 833s",
                            "Introduce Yourself",
                            "Tickets",
                            "Server Info",
                        ]
                    ):
                        already = True
                        break
                if already:
                    continue
                msg = await ch.send(body)
                try:
                    await msg.pin(reason="Bootstrap pinned")
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.4)
            except discord.HTTPException:
                continue

    def _rules_text(self) -> str:
        return (
            "**Server Rules (Summary)**\n"
            "1) Respect others.\n"
            "2) No spam, scams, or malicious links.\n"
            "3) Keep content in the right channels.\n"
            "4) Follow staff instructions during moderation.\n"
            "Use /ticket in #tickets for private support."
        )

    def _introductions_text(self) -> str:
        return (
            "**Introduce Yourself**\n"
            "Name / nickname, interests, what you play/build, and what you want from 833s.\n"
            "Optional: add a project link or screenshot."
        )

    def _welcome_text(self) -> str:
        return (
            "**Welcome to 833’s**\n"
            "This server is structured. Use the right channels, keep things tidy, and the systems will scale.\n"
            "Start in #verify, then read #rules and #server-info."
        )

    def _tickets_text(self) -> str:
        return (
            "**Tickets**\n"
            "Use /ticket to open a private support thread.\n"
            "Include what happened, what you expected, and screenshots if relevant."
        )

    def _server_info_text(self) -> str:
        return (
            "**Server Info**\n"
            "This server is built around structured routing (games, dev, pets).\n"
            "If you are unsure where something belongs, check the category names and pinned messages first."
        )
