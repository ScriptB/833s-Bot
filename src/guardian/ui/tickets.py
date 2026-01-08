from __future__ import annotations

import discord


class TicketCreateView(discord.ui.View):
    def __init__(self, bot, guild_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.success, custom_id="ticket_open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Guild missing.", ephemeral=True)
            return

        existing = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.id}")
        if existing:
            await interaction.response.send_message(f"Ticket already open: {existing.mention}", ephemeral=True)
            return

        staff_roles = [discord.utils.get(guild.roles, name=n) for n in ("Admin", "Moderator", "Helper")]
        staff_roles = [r for r in staff_roles if r]

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        for r in staff_roles:
            overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)

        cat = discord.utils.get(guild.categories, name="SUPPORT")
        if not cat:
            cat = await guild.create_category("SUPPORT")

        ch = await guild.create_text_channel(name=f"ticket-{interaction.user.id}", category=cat, overwrites=overwrites, reason="Ticket opened")
        await ch.send(f"{interaction.user.mention} Describe your issue. Staff will respond.")
        await interaction.response.send_message(f"Ticket created: {ch.mention}", ephemeral=True)
