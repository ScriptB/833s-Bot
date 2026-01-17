from __future__ import annotations

import asyncio

import discord
from discord.ext import commands


class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self.bot.task_queue.enqueue(lambda: self._handle_join(member))  # type: ignore[attr-defined]

    async def _handle_join(self, member: discord.Member) -> None:
        cfg = await self.bot.guild_store.get(member.guild.id)  # type: ignore[attr-defined]

        # Autorole
        if cfg.autorole_id:
            role = member.guild.get_role(cfg.autorole_id)
            if role:
                try:
                    await member.add_roles(role, reason="833's Guardian autorole")
                    self.bot.stats.roles_assigned += 1  # type: ignore[attr-defined]
                    await asyncio.sleep(0.2)
                except (discord.Forbidden, discord.HTTPException):
                    pass

        # Welcome message (send DM instead of public channel)
        try:
            embed = discord.Embed(
                title="Welcome to the server!",
                description=(
                    f"Hey {member.mention} — welcome!\n\n"
                    "• Read the rules in #rules\n"
                    "• Verify in #verify to get access\n"
                    "• Pick roles in #reaction-roles\n"
                    "• Enjoy your stay! 🎯"
                ),
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await member.send(embed=embed)
            self.bot.stats.welcomes_sent += 1  # type: ignore[attr-defined]
            await asyncio.sleep(0.2)
        except discord.HTTPException:
            pass

        # Log
        await self.bot.guild_logger.send(  # type: ignore[attr-defined]
            member.guild,
            cfg.log_channel_id,
            f"✅ Member joined: {member.mention} (`{member.id}`)",
        )

    # welcome_backfill command removed from production
