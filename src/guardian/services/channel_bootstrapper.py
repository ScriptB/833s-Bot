from __future__ import annotations

import asyncio

import discord

from ..utils import find_text_channel_fuzzy


class ChannelBootstrapper:
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot

    async def ensure_first_posts(self, guild: discord.Guild) -> None:
        targets = {
            "rules": self._rules_text(),
            "introductions": self._introductions_text(),
            "tickets": self._help_text(),
            "verify": self._help_verification_text(),
            "welcome": self._start_here_text(),
        }
        for name, body in targets.items():
            ch = find_text_channel_fuzzy(guild, name)
            if not isinstance(ch, discord.TextChannel):
                continue
            try:
                # Check for existing bootstrap posts (without marker)
                already = False
                async for m in ch.history(limit=15, oldest_first=True):
                    if m.author == guild.me and m.content and any(text in m.content for text in ["Server Rules", "Introduce Yourself", "Help & Support", "Verification Help", "Welcome to 833s"]):
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
            "Use /ticket_panel in #tickets for private support."
        )

    def _introductions_text(self) -> str:
        return (
            "**Introduce Yourself**\n"
            "Name / nickname, interests, what you play/build, and what you want from 833s.\n"
            "Optional: add a project link or screenshot."
        )

    def _help_text(self) -> str:
        return (
            "**Help & Support**\n"
            "Use the buttons in #tickets for private support.\n"
            "For quick help: describe the issue + screenshots + what you tried."
        )

    def _help_verification_text(self) -> str:
        return (
            "**Verification Help**\n"
            "Complete verification to unlock server features.\n"
            "Follow the instructions in #verify.\n"
            "Contact staff if you encounter any issues."
        )

    def _start_here_text(self) -> str:
        return (
            "**Welcome to 833s**\n"
            "Complete onboarding in #verify to unlock the server.\n"
            "After verification: check #announcements and #server-info."
        )
