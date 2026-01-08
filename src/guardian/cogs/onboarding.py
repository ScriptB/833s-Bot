from __future__ import annotations

import discord
from discord.ext import commands

from ..ui.onboarding import OnboardingView


class OnboardingCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        quarantine = discord.utils.get(guild.roles, name="Quarantine")
        if quarantine:
            try:
                await member.add_roles(quarantine, reason="Onboarding quarantine")
            except discord.HTTPException:
                pass

        try:
            await self.bot.onboarding_store.get(guild.id, member.id)  # type: ignore[attr-defined]
        except Exception:
            pass

        ch = discord.utils.get(guild.text_channels, name="verify")
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
