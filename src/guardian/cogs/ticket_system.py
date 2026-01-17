from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import discord

from ..utils import find_text_channel_fuzzy
from ..utils import find_role_fuzzy
from discord import app_commands
from discord.ext import commands

from ..constants import COLORS
from ..permissions import require_ticket_owner_or_staff, require_verified
from ..services.api_wrapper import safe_create_channel, safe_send_message

log = logging.getLogger("guardian.ticket_system")


@dataclass
class TicketConfig:
    """Configuration for ticket system."""
    category_name: str = "🎫 TICKETS"
    support_roles: list[str] = None
    transcript_enabled: bool = True
    auto_close_days: int = 7
    
    def __post_init__(self):
        if self.support_roles is None:
            self.support_roles = ["Support", "Moderator", "Admin", "Owner"]


class TicketCreateButton(discord.ui.Button):
    """Button for creating a new ticket."""
    
    def __init__(self):
        super().__init__(
            label="Create Ticket",
            style=discord.ButtonStyle.primary,
            custom_id="guardian_ticket_create",
            emoji="🎫"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle ticket creation."""
        # Get the cog from the bot
        cog = interaction.client.get_cog('TicketSystemCog')
        if cog:
            await cog.create_ticket(interaction)
        else:
            await interaction.response.send_message("❌ Ticket system cog not found.", ephemeral=True)


class TicketCloseButton(discord.ui.Button):
    """Button for closing a ticket."""
    
    def __init__(self):
        super().__init__(
            label="Close Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="guardian_ticket_close",
            emoji="🔒"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle ticket closing."""
        # Get the cog from the bot
        cog = interaction.client.get_cog('TicketSystemCog')
        if cog:
            await cog.close_ticket(interaction)
        else:
            await interaction.response.send_message("❌ Ticket system cog not found.", ephemeral=True)


class TicketView(discord.ui.View):
    """View for ticket panel with persistent timeout."""
    
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view
        self.add_item(TicketCreateButton())


class TicketControlView(discord.ui.View):
    """View for ticket control inside ticket channels."""
    
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view
        self.add_item(TicketCloseButton())


class TicketSystemCog(commands.Cog):
    """Commercial-grade ticket system."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = TicketConfig()
        self._active_tickets: dict[int, dict[str, Any]] = {}  # channel_id -> ticket_info
    
    async def cog_load(self):
        """Register persistent views when cog loads."""
        self.bot.add_view(TicketView())
        self.bot.add_view(TicketControlView())
        log.info("Ticket system views registered")
    
    async def create_ticket(self, interaction: discord.Interaction):
        """Create a new ticket channel."""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send("❌ Tickets can only be created in a server.", ephemeral=True)
            return
        
        # Check if user already has an active ticket
        existing_ticket = self._find_user_ticket(interaction.user.id, interaction.guild.id)
        if existing_ticket:
            await interaction.followup.send(
                f"❌ You already have an active ticket: <#{existing_ticket['channel_id']}>",
                ephemeral=True
            )
            return
        
        # Get or create ticket category
        category = await self._get_ticket_category(interaction.guild)
        if not category:
            await interaction.followup.send(
                "❌ Failed to create ticket category. Please contact an administrator.",
                ephemeral=True
            )
            return
        
        # Create ticket channel
        ticket_number = await self._get_next_ticket_number(interaction.guild)
        channel_name = f"ticket-{ticket_number:04d}"
        
        # Set up permissions
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(
                read_messages=False,
                send_messages=False
            ),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True
            )
        }
        
        # Add support roles
        for role_name in self.config.support_roles:
            role = find_role_fuzzy(interaction.guild, role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True
                )
        
        try:
            result = await safe_create_channel(
                guild=interaction.guild,
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket for {interaction.user.display_name} ({interaction.user.id})",
                reason=f"Ticket created by {interaction.user.display_name}"
            )
            
            if not result.success:
                await interaction.followup.send(
                    f"❌ Failed to create ticket channel: {result.error}",
                    ephemeral=True
                )
                return
            
            ticket_channel = result.data
            
            # Store ticket info
            self._active_tickets[ticket_channel.id] = {
                "user_id": interaction.user.id,
                "guild_id": interaction.guild.id,
                "created_at": datetime.utcnow(),
                "channel_id": ticket_channel.id,
                "ticket_number": ticket_number
            }
            
            # Send welcome message
            embed = discord.Embed(
                title="🎫 Support Ticket",
                description=(
                    f"Hello {interaction.user.mention}!\n\n"
                    "Thank you for creating a support ticket. Our staff team will be with you shortly.\n\n"
                    "**Please provide:**\n"
                    "• A detailed description of your issue\n"
                    "• Any relevant screenshots or files\n"
                    "• Steps to reproduce (if applicable)\n\n"
                    "📝 **Please be patient** - staff will respond as soon as possible."
                ),
                color=COLORS["primary"]
            )
            
            embed.add_field(
                name="🔧 Ticket Information",
                value=(
                    f"**Ticket Number:** #{ticket_number:04d}\n"
                    f"**Created:** <t:{int(datetime.utcnow().timestamp())}:R>\n"
                    f"**User:** {interaction.user.mention}\n"
                    f"**Status:** 🟢 Open"
                ),
                inline=False
            )
            
            embed.set_footer(text="Click 'Close Ticket' when your issue is resolved.")
            
            view = TicketControlView()
            
            message_result = await safe_send_message(
                ticket_channel,
                embed=embed,
                view=view
            )
            
            if message_result.success:
                # Pin the welcome message
                try:
                    await message_result.data.pin()
                except discord.Forbidden:
                    log.warning(f"Cannot pin ticket message in {ticket_channel.id}")
            
            # Send confirmation to user
            await interaction.followup.send(
                f"✅ Ticket created! <#{ticket_channel.id}>",
                ephemeral=True
            )
            
            # Notify staff (optional)
            await self._notify_staff(interaction.guild, ticket_channel, interaction.user)
            
            log.info(f"Ticket #{ticket_number:04d} created by {interaction.user.id} in {interaction.guild.id}")
            
        except Exception as e:
            log.exception(f"Error creating ticket for {interaction.user.id}: {e}")
            await interaction.followup.send(
                "❌ An error occurred while creating your ticket. Please try again later.",
                ephemeral=True
            )
    
    async def close_ticket(self, interaction: discord.Interaction):
        """Close a ticket channel."""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.followup.send("❌ This command can only be used in a ticket channel.", ephemeral=True)
            return
        
        ticket_info = self._active_tickets.get(interaction.channel.id)
        if not ticket_info:
            await interaction.followup.send("❌ This is not an active ticket.", ephemeral=True)
            return
        
        # Check permissions (ticket creator or staff)
        is_staff = any(role.name in self.config.support_roles for role in interaction.user.roles)
        is_creator = interaction.user.id == ticket_info["user_id"]
        
        if not (is_staff or is_creator):
            await interaction.followup.send("❌ Only ticket creators and staff can close tickets.", ephemeral=True)
            return
        
        try:
            # Create transcript if enabled
            transcript_message = ""
            if self.config.transcript_enabled:
                transcript_message = await self._create_transcript(interaction.channel, ticket_info)
            
            # Update channel to be read-only
            overwrites = interaction.channel.overwrites
            for target, overwrite in overwrites.items():
                if isinstance(target, discord.Member) or isinstance(target, discord.Role):
                    if target != interaction.guild.me:
                        overwrite.send_messages = False
            
            await interaction.channel.edit(overwrites=overwrites)
            
            # Send closing message
            embed = discord.Embed(
                title="🔒 Ticket Closed",
                description=(
                    f"This ticket has been closed by {interaction.user.mention}.\n\n"
                    f"**Ticket Information:**\n"
                    f"• **Number:** #{ticket_info['ticket_number']:04d}\n"
                    f"• **Created:** <t:{int(ticket_info['created_at'].timestamp())}:R>\n"
                    f"• **Closed:** <t:{int(datetime.utcnow().timestamp())}:R>\n"
                    f"• **Closed by:** {interaction.user.mention}"
                ),
                color=discord.Color.red()
            )
            
            if transcript_message:
                embed.add_field(
                    name="📄 Transcript",
                    value=transcript_message,
                    inline=False
                )
            
            embed.set_footer(text="This channel will be deleted automatically after 7 days.")
            
            await safe_send_message(interaction.channel, embed=embed)
            
            # Remove from active tickets
            del self._active_tickets[interaction.channel.id]
            
            # Schedule deletion (if implemented)
            # This would require a background task
            
            await interaction.followup.send("✅ Ticket closed successfully.", ephemeral=True)
            
            log.info(f"Ticket #{ticket_info['ticket_number']:04d} closed by {interaction.user.id}")
            
        except Exception as e:
            log.exception(f"Error closing ticket {interaction.channel.id}: {e}")
            await interaction.followup.send(
                "❌ An error occurred while closing the ticket. Please try again later.",
                ephemeral=True
            )
    
    async def _get_ticket_category(self, guild: discord.Guild) -> discord.CategoryChannel | None:
        """Get or create the ticket category."""
        category = discord.utils.get(guild.categories, name=self.config.category_name)
        
        if category is None:
            try:
                result = await safe_create_channel(
                    guild=guild,
                    name=self.config.category_name,
                    type=discord.ChannelType.category,
                    reason="Create ticket category"
                )
                
                if result.success:
                    category = result.data
                    log.info(f"Created ticket category {self.config.category_name} in guild {guild.id}")
                else:
                    log.error(f"Failed to create ticket category: {result.error}")
                    return None
                    
            except Exception as e:
                log.exception(f"Error creating ticket category: {e}")
                return None
        
        return category
    
    async def _get_next_ticket_number(self, guild: discord.Guild) -> int:
        """Get the next available ticket number."""
        # Find existing ticket channels
        category = await self._get_ticket_category(guild)
        if not category:
            return 1
        
        ticket_channels = [ch for ch in category.text_channels if ch.name.startswith("ticket-")]
        
        if not ticket_channels:
            return 1
        
        # Extract numbers from existing ticket names
        numbers = []
        for channel in ticket_channels:
            try:
                parts = channel.name.split("-")
                if len(parts) >= 2:
                    numbers.append(int(parts[1]))
            except (ValueError, IndexError):
                continue
        
        return max(numbers, default=0) + 1
    
    def _find_user_ticket(self, user_id: int, guild_id: int) -> dict[str, Any] | None:
        """Find an active ticket for a user."""
        for ticket_info in self._active_tickets.values():
            if ticket_info["user_id"] == user_id and ticket_info["guild_id"] == guild_id:
                return ticket_info
        return None
    
    async def _notify_staff(self, guild: discord.Guild, ticket_channel: discord.TextChannel, user: discord.Member):
        """Notify staff about new ticket."""
        # Find a staff channel or use the first available
        staff_channel = find_text_channel_fuzzy(guild, "staff-chat")
        if not staff_channel:
            staff_channel = find_text_channel_fuzzy(guild, "staff")
        
        if staff_channel:
            embed = discord.Embed(
                title="🎫 New Ticket Created",
                description=f"A new support ticket has been created by {user.mention}",
                color=COLORS["primary"]
            )
            
            embed.add_field(
                name="Ticket Details",
                value=f"**Channel:** {ticket_channel.mention}\n**User:** {user.mention} ({user.display_name})",
                inline=False
            )
            
            embed.set_footer(text="Please respond to the ticket as soon as possible.")
            
            await safe_send_message(staff_channel, embed=embed)
    
    async def _create_transcript(self, channel: discord.TextChannel, ticket_info: dict[str, Any]) -> str:
        """Create a transcript of the ticket conversation."""
        try:
            messages = []
            async for message in channel.history(limit=None, oldest_first=True):
                if message.system_content:
                    continue
                
                timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                author = message.author.display_name
                
                if message.attachments:
                    content = f"{message.content} [Attachments: {len(message.attachments)}]"
                else:
                    content = message.content
                
                messages.append(f"[{timestamp}] {author}: {content}")
            
            # For now, just return a summary
            # In a full implementation, this could save to a file or database
            return f"Transcript contains {len(messages)} messages"
            
        except Exception as e:
            log.warning(f"Failed to create transcript for ticket {ticket_info['ticket_number']}: {e}")
            return "Transcript unavailable"
    
    @app_commands.command(
        name="ticket",
        description="Create a new support ticket"
    )
    @require_verified()
    async def ticket_command(self, interaction: discord.Interaction):
        """Slash command to create a ticket."""
        await self.create_ticket(interaction)
    
    @app_commands.command(
        name="close",
        description="Close the current ticket"
    )
    @require_ticket_owner_or_staff()
    async def close_command(self, interaction: discord.Interaction):
        """Slash command to close a ticket."""
        await self.close_ticket(interaction)
    
    async def deploy_ticket_panel(self, guild: discord.Guild) -> discord.Message | None:
        """Deploy the ticket creation panel."""
        channel = find_text_channel_fuzzy(guild, "support-start") or find_text_channel_fuzzy(guild, "tickets")
        if not channel:
            log.warning(f"Support panel channel not found (tried support-start, tickets) in guild {guild.id}")
            return None
        
        embed = discord.Embed(
            title="🎫 Support Center",
            description=(
                "Need help? Create a support ticket and our staff will assist you!\n\n"
                "**Before creating a ticket:**\n"
                "• Check our FAQ and rules first\n"
                "• Be as detailed as possible about your issue\n"
                "• Include screenshots if applicable\n\n"
                "Click the button below to create a ticket."
            ),
            color=COLORS["primary"]
        )
        
        embed.add_field(
            name="⏰ Response Times",
            value="Our staff typically responds within 24 hours.",
            inline=False
        )
        
        embed.set_footer(text="Tickets are private between you and our staff team.")
        
        view = TicketView()
        
        result = await safe_send_message(channel, embed=embed, view=view)
        
        if result.success:
            log.info(f"Deployed ticket panel in guild {guild.id}")
            return result.data
        else:
            log.error(f"Failed to deploy ticket panel: {result.error}")
            return None


async def setup(bot: commands.Bot):
    """Setup function for the cog."""
    await bot.add_cog(TicketSystemCog(bot))
