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
        views_registered = 0
        
        # Register verification view
        try:
            verify_view = VerifyView()
            bot.add_view(verify_view)
            views_registered += 1
            log.info("Registered persistent VerifyView")
        except Exception as e:
            log.warning(f"Failed to register VerifyView: {e}")
        
        # Register role selection view
        try:
            role_view = RoleSelectView([])
            bot.add_view(role_view)
            views_registered += 1
            log.info("Registered persistent RoleSelectView")
        except Exception as e:
            log.warning(f"Failed to register RoleSelectView: {e}")
        
        # Register ticket creation view
        try:
            from guardian.cogs.ticket_system import TicketCreateView
            ticket_view = TicketCreateView()
            bot.add_view(ticket_view)
            views_registered += 1
            log.info("Registered persistent TicketCreateView")
        except Exception as e:
            log.warning(f"Failed to register TicketCreateView: {e}")
        
        # Register ticket control view
        try:
            from guardian.cogs.ticket_system import TicketControlView
            ticket_control_view = TicketControlView()
            bot.add_view(ticket_control_view)
            views_registered += 1
            log.info("Registered persistent TicketControlView")
        except Exception as e:
            log.warning(f"Failed to register TicketControlView: {e}")
        
        # Register role assignment view
        try:
            from guardian.cogs.role_assignment import RoleSelectView as RoleAssignmentView
            role_assignment_view = RoleAssignmentView()
            bot.add_view(role_assignment_view)
            views_registered += 1
            log.info("Registered persistent RoleAssignmentView")
        except Exception as e:
            log.warning(f"Failed to register RoleAssignmentView: {e}")
        
        # Register overhaul confirmation view
        try:
            from guardian.cogs.overhaul import OverhaulConfirmationView
            overhaul_view = OverhaulConfirmationView()
            bot.add_view(overhaul_view)
            views_registered += 1
            log.info("Registered persistent OverhaulConfirmationView")
        except Exception as e:
            log.warning(f"Failed to register OverhaulConfirmationView: {e}")
        
        # Set persistent views flag for diagnostics
        bot._persistent_views_registered = views_registered > 0
        log.info(f"Registered {views_registered} persistent views successfully")
        
    except Exception as e:
        log.exception(f"Failed to register persistent views: {e}")
        bot._persistent_views_registered = False


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
