from __future__ import annotations

import discord
from discord.ext import commands

from ..utils.lookup import find_text_channel, find_role

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
                verify_channel = find_text_channel(guild, "verify")
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
        quarantine = find_role(guild, "Quarantine")
        if quarantine:
            try:
                await member.add_roles(quarantine, reason="Onboarding quarantine")
            except discord.HTTPException:
                pass

        try:
            await self.bot.onboarding_store.get(guild.id, member.id)  # type: ignore[attr-defined]
        except Exception:
            pass

        ch = find_text_channel(guild, "verify")
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
        if getattr(message.channel, "name", "") != "verify":
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
