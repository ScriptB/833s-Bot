from __future__ import annotations

import discord


class GiveawayJoinButton(discord.ui.Button):
    def __init__(self, guild_id: int, message_id: int):
        super().__init__(label="Join Giveaway", style=discord.ButtonStyle.success, custom_id=f"gw:join:{guild_id}:{message_id}")

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        bot = interaction.client  # type: ignore
        gid = interaction.guild.id
        mid = int(self.custom_id.split(":")[-1])
        count = await bot.giveaways_store.add_entry(gid, mid, interaction.user.id)  # type: ignore
        await interaction.response.send_message(f"✅ Joined. Entries: {count}", ephemeral=True)


class GiveawayLeaveButton(discord.ui.Button):
    def __init__(self, guild_id: int, message_id: int):
        super().__init__(label="Leave", style=discord.ButtonStyle.secondary, custom_id=f"gw:leave:{guild_id}:{message_id}")

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        bot = interaction.client  # type: ignore
        gid = interaction.guild.id
        mid = int(self.custom_id.split(":")[-1])
        count = await bot.giveaways_store.remove_entry(gid, mid, interaction.user.id)  # type: ignore
        await interaction.response.send_message(f"✅ Left. Entries: {count}", ephemeral=True)


class GiveawayView(discord.ui.View):
    def __init__(self, guild_id: int, message_id: int):
        super().__init__(timeout=None)
        self.add_item(GiveawayJoinButton(guild_id, message_id))
        self.add_item(GiveawayLeaveButton(guild_id, message_id))
