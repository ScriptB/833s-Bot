from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

STAR = "⭐"


class StarboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot  # type: ignore[assignment]

    @app_commands.command(name="starboard_set", description="Set starboard channel and threshold.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def starboard_set(self, interaction: discord.Interaction, channel: discord.TextChannel, threshold: app_commands.Range[int, 1, 20] = 3) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        await self.bot.starboard_store.set_config(interaction.guild.id, channel.id, int(threshold))  # type: ignore[attr-defined]
        await interaction.followup.send("✅ Starboard configured.", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if str(payload.emoji) != STAR or not payload.guild_id:
            return
        await self._handle(payload.guild_id, payload.channel_id, payload.message_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if str(payload.emoji) != STAR or not payload.guild_id:
            return
        await self._handle(payload.guild_id, payload.channel_id, payload.message_id)

    async def _handle(self, guild_id: int, channel_id: int, message_id: int) -> None:
        cfg = await self.bot.starboard_store.get_config(guild_id)  # type: ignore[attr-defined]
        if not cfg:
            return
        star_channel_id, threshold = cfg

        guild = self.bot.get_guild(guild_id)  # type: ignore[attr-defined]
        if not guild:
            return
        src_channel = guild.get_channel(channel_id)
        if not isinstance(src_channel, discord.TextChannel):
            return
        try:
            msg = await src_channel.fetch_message(message_id)
        except discord.HTTPException:
            return

        stars = 0
        for r in msg.reactions:
            if str(r.emoji) == STAR:
                stars = r.count
                break

        existing = await self.bot.starboard_store.get_post(guild_id, message_id)  # type: ignore[attr-defined]
        if stars < threshold and not existing:
            return

        sb_channel = guild.get_channel(star_channel_id)
        if not isinstance(sb_channel, discord.TextChannel):
            return

        embed = discord.Embed(description=msg.content or "", timestamp=msg.created_at)
        embed.set_author(name=str(msg.author), icon_url=msg.author.display_avatar.url)
        embed.add_field(name="Jump", value=f"[Go to message]({msg.jump_url})", inline=False)
        if msg.attachments:
            a = msg.attachments[0]
            if a.content_type and a.content_type.startswith("image/"):
                embed.set_image(url=a.url)

        content = f"{STAR} **{stars}** in <#{channel_id}>"

        try:
            if not existing:
                sb_msg = await sb_channel.send(content=content, embed=embed)
                await self.bot.starboard_store.upsert_post(guild_id, message_id, sb_msg.id, stars)  # type: ignore[attr-defined]
            else:
                sb_mid, _old = existing
                try:
                    sb_msg = await sb_channel.fetch_message(sb_mid)
                    await sb_msg.edit(content=content, embed=embed)
                    await self.bot.starboard_store.upsert_post(guild_id, message_id, sb_mid, stars)  # type: ignore[attr-defined]
                except discord.HTTPException:
                    sb_msg = await sb_channel.send(content=content, embed=embed)
                    await self.bot.starboard_store.upsert_post(guild_id, message_id, sb_msg.id, stars)  # type: ignore[attr-defined]
        except discord.HTTPException:
            return
