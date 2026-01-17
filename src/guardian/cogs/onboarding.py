from __future__ import annotations

import discord

from ..utils import find_text_channel_fuzzy
from discord.ext import commands

from ..ui.onboarding import OnboardingView


class OnboardingCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Re-attach persistent onboarding views on bot startup."""
        for guild in self.bot.guilds:
            try:
                # Find existing onboarding messages
                verify_name = getattr(self.bot.settings, "verify_channel_name", "verify")
                verify_channel = find_text_channel_fuzzy(guild, verify_name)
                if verify_channel:
                    async for message in verify_channel.history(limit=20):
                        if "Mandatory Onboarding" in (message.embeds[0].title if message.embeds else ""):
                            # Re-attach view to existing onboarding message
                            # Note: We can't easily determine user_id from message, so we'll use a generic view
                            view = OnboardingView(self.bot, guild.id, 0)
                            self.bot.add_view(view, message_id=message.id)
                            break
            except Exception:
                continue

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        from ..utils import find_role_fuzzy
        quarantine_name = getattr(self.bot.settings, "quarantine_role_name", "Quarantine")
        quarantine = find_role_fuzzy(guild, quarantine_name)
        if quarantine:
            try:
                await member.add_roles(quarantine, reason="Onboarding quarantine")
            except discord.HTTPException:
                pass

        try:
            await self.bot.onboarding_store.get(guild.id, member.id)  # type: ignore[attr-defined]
        except Exception:
            pass

        verify_name = getattr(self.bot.settings, "verify_channel_name", "verify")
        ch = find_text_channel_fuzzy(guild, verify_name)
        if not ch:
            return
        try:
            view = OnboardingView(self.bot, guild.id, member.id)
            self.bot.add_view(view)  # type: ignore[attr-defined]
            embed = discord.Embed(
                title="Mandatory Onboarding",
                description=(
                    "1) Accept Rules\n"
                    "2) Confirm 18+\n"
                    "3) Select language + interests\n"
                    "4) Finish\n\n"
                    "Access is locked until completion."
                ),
            )
            await ch.send(content=member.mention, embed=embed, view=view)
        except discord.HTTPException:
            return

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        verify_name = getattr(self.bot.settings, "verify_channel_name", "verify")
        verify_ch = find_text_channel_fuzzy(message.guild, verify_name)
        if not verify_ch or message.channel.id != verify_ch.id:
            return
        if message.content.strip().lower() not in {"i agree", "i accept"}:
            return
        st = await self.bot.onboarding_store.get(message.guild.id, message.author.id)  # type: ignore[attr-defined]
        if st.step < 1:
            await self.bot.onboarding_store.upsert(type(st)(st.guild_id, st.user_id, 1, st.language, st.interests_json, st.completed))  # type: ignore[attr-defined]
            try:
                await message.reply("Rules accepted. Continue with the buttons above.", mention_author=False)
            except discord.HTTPException:
                pass
