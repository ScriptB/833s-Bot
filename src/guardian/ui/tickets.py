from __future__ import annotations

import discord

from ..utils.lookup import find_text_channel, find_role, find_category


class TicketCreateView(discord.ui.View):
    """Persistent ticket creation view that survives bot restarts."""
    
    def __init__(self, bot, guild_id: int) -> None:
        super().__init__(timeout=None)  # Persistent view
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

        staff_roles = [find_role(guild, n) for n in ("Admin", "Moderator", "Support")]
        staff_roles = [r for r in staff_roles if r]

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        for r in staff_roles:
            overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)

        cat = find_category(guild, "SUPPORT") or find_category(guild, "🆘 SUPPORT")
        if not cat:
            await interaction.response.send_message(
                "❌ SUPPORT category not found. Please contact an administrator to set up the ticket system.",
                ephemeral=True
            )
            return

        ch = await guild.create_text_channel(name=f"ticket-{interaction.user.id}", category=cat, overwrites=overwrites, reason="Ticket opened")
        await ch.send(f"{interaction.user.mention} Describe your issue. Staff will respond.")
        await interaction.response.send_message(f"Ticket created: {ch.mention}", ephemeral=True)
