from __future__ import annotations

import discord
from discord.ext import commands


class VoiceRoomsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]
        self._created: dict[int, int] = {}

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        guild = member.guild
        create = discord.utils.get(guild.voice_channels, name="➕ create-room")
        if not create:
            return

        if after.channel and after.channel.id == create.id:
            cat = create.category
            base = f"room-{member.display_name}".lower().replace(" ", "-")
            name = base[:90] if base else f"room-{member.id}"
            ch = await guild.create_voice_channel(name=name, category=cat, reason="Temp voice room")
            self._created[member.id] = ch.id
            try:
                await member.move_to(ch)
            except discord.HTTPException:
                pass

        if before.channel and before.channel.id in set(self._created.values()):
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Temp voice room cleanup")
                except discord.HTTPException:
                    pass
