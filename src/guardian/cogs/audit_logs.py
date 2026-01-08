from __future__ import annotations

import discord
from discord.ext import commands


class AuditLogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    def _ch(self, guild: discord.Guild, name: str) -> discord.TextChannel | None:
        ch = discord.utils.get(guild.text_channels, name=name)
        return ch if isinstance(ch, discord.TextChannel) else None

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        ch = self._ch(message.guild, "message-logs")
        if not ch:
            return
        e = discord.Embed(title="Message Deleted")
        e.add_field(name="Author", value=f"{message.author} ({message.author.id})", inline=False)
        e.add_field(name="Channel", value=f"#{message.channel}", inline=False)
        if message.content:
            e.add_field(name="Content", value=message.content[:1000], inline=False)
        await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not after.guild or after.author.bot:
            return
        if before.content == after.content:
            return
        ch = self._ch(after.guild, "message-logs")
        if not ch:
            return
        e = discord.Embed(title="Message Edited")
        e.add_field(name="Author", value=f"{after.author} ({after.author.id})", inline=False)
        e.add_field(name="Channel", value=f"#{after.channel}", inline=False)
        e.add_field(name="Before", value=(before.content or "—")[:700], inline=False)
        e.add_field(name="After", value=(after.content or "—")[:700], inline=False)
        await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.roles == after.roles:
            return
        ch = self._ch(after.guild, "role-logs")
        if not ch:
            return
        b = {r.id for r in before.roles}
        a = {r.id for r in after.roles}
        added = [r.name for r in after.roles if r.id in (a - b)]
        removed = [r.name for r in before.roles if r.id in (b - a)]
        e = discord.Embed(title="Role Change")
        e.add_field(name="Member", value=f"{after} ({after.id})", inline=False)
        if added:
            e.add_field(name="Added", value=", ".join(added)[:900], inline=False)
        if removed:
            e.add_field(name="Removed", value=", ".join(removed)[:900], inline=False)
        await ch.send(embed=e)
