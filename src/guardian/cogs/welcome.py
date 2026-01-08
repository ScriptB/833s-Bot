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

        # Welcome message
        if cfg.welcome_channel_id:
            channel = member.guild.get_channel(cfg.welcome_channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    embed = discord.Embed(
                        title="Welcome to the server!",
                        description=(
                            f"Hey {member.mention} — welcome in.\n\n"
                            "• Check the rules\n"
                            "• Grab roles if available\n"
                            "• Say hi and enjoy your stay 👊"
                        ),
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    await channel.send(embed=embed)
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

    @commands.hybrid_command(name="welcome_backfill", description="Queue welcome jobs for the last N cached members.")
    @commands.has_permissions(manage_guild=True)
    async def welcome_backfill(self, ctx: commands.Context, count: int = 10) -> None:
        if not ctx.guild:
            return

        count = max(1, min(50, int(count)))
        members = list(ctx.guild.members)[-count:]
        members.reverse()

        for m in members:
            await self.bot.task_queue.enqueue(lambda mm=m: self._handle_join(mm))  # type: ignore[attr-defined]

        await ctx.reply(f"✅ Enqueued **{len(members)}** welcome jobs. They will run gradually.")
