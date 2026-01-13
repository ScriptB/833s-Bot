from __future__ import annotations

import discord
from discord import ui
import logging

log = logging.getLogger("guardian.ui.persistent")


# Stable custom_id namespace
GUARDIAN_V1 = "guardian:v1"


class VerifyView(ui.View):
    """Persistent verification panel view."""
    
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view
    
    @ui.button(label="Verify", style=discord.ButtonStyle.success, custom_id=f"{GUARDIAN_V1}:verify:accept")
    async def verify_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle verification button click."""
        # This will be implemented in the verify_panel cog
        pass


class RoleSelectView(ui.View):
    """Persistent role selection panel view."""
    
    def __init__(self, role_options: list):
        super().__init__(timeout=None)  # Persistent view
        self.role_options = role_options
        
        # Add role selection dropdown
        self.add_item(RoleSelectDropdown(role_options))


class RoleSelectDropdown(ui.Select):
    """Role selection dropdown with stable custom_id."""
    
    def __init__(self, role_options: list):
        options = [
            discord.SelectOption(
                label=opt["label"],
                value=opt["value"],
                description=opt.get("description"),
                emoji=opt.get("emoji")
            )
            for opt in role_options
        ]
        
        super().__init__(
            placeholder="Select roles to add/remove",
            min_values=1,
            max_values=len(options),
            options=options,
            custom_id=f"{GUARDIAN_V1}:roleselect:menu"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle role selection."""
        # This will be implemented in the role_panel cog
        pass


class TicketCreateView(ui.View):
    """Persistent ticket creation panel view."""
    
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view
    
    @ui.button(label="Create Ticket", style=discord.ButtonStyle.primary, custom_id=f"{GUARDIAN_V1}:ticket:create")
    async def create_ticket(self, interaction: discord.Interaction, button: ui.Button):
        """Handle ticket creation."""
        # This will be implemented in the tickets cog
        pass


# Registry function to register all persistent views
def register_all_views(bot: discord.Client) -> None:
    """Register all persistent views with the bot."""
    try:
        # Register verification view
        verify_view = VerifyView()
        bot.add_view(verify_view)
        log.info("Registered persistent VerifyView")
        
        # Register role selection view (placeholder - will be configured per guild)
        role_view = RoleSelectView([])
        bot.add_view(role_view)
        log.info("Registered persistent RoleSelectView")
        
        # Register ticket creation view
        ticket_view = TicketCreateView()
        bot.add_view(ticket_view)
        log.info("Registered persistent TicketCreateView")
        
        log.info("All persistent views registered successfully")
        
    except Exception as e:
        log.exception(f"Failed to register persistent views: {e}")
        raise


# View factory functions for creating configured views
def create_verify_view() -> VerifyView:
    """Create a verification view."""
    return VerifyView()


def create_role_select_view(role_options: list) -> RoleSelectView:
    """Create a role selection view with configured options."""
    return RoleSelectView(role_options)


def create_ticket_view() -> TicketCreateView:
    """Create a ticket creation view."""
    return TicketCreateView()
