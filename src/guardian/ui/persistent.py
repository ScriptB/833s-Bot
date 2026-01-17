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
    registration_results = {
        'attempted': 0,
        'succeeded': 0,
        'failed': 0,
        'failures': []
    }
    
    views_to_register = [
        ('VerifyView', lambda: VerifyView()),
        ('RoleSelectView', lambda: RoleSelectView([])),
        ('TicketView', lambda: _import_and_create('guardian.cogs.ticket_system', 'TicketView')),
        ('TicketControlView', lambda: _import_and_create('guardian.cogs.ticket_system', 'TicketControlView')),
        ('RoleAssignmentView', lambda: _import_and_create('guardian.cogs.role_assignment', 'RoleSelectView')),
    ]
    
    def _import_and_create(module_name: str, class_name: str):
        """Import and create a view instance."""
        module = __import__(module_name, fromlist=[class_name])
        view_class = getattr(module, class_name)
        return view_class()
    
    for view_name, view_factory in views_to_register:
        registration_results['attempted'] += 1
        try:
            view = view_factory()
            bot.add_view(view)
            registration_results['succeeded'] += 1
            log.info(f"✅ Registered persistent {view_name}")
        except Exception as e:
            registration_results['failed'] += 1
            error_msg = f"❌ Failed to register {view_name}: {type(e).__name__}: {str(e)}"
            registration_results['failures'].append(error_msg)
            log.warning(error_msg)
    
    # Set persistent views flag for diagnostics
    bot._persistent_views_registered = registration_results['succeeded'] > 0
    bot._persistent_views_stats = registration_results
    
    # Log comprehensive summary
    log.info(f"📊 Persistent Views Registration Summary:")
    log.info(f"   Attempted: {registration_results['attempted']}")
    log.info(f"   Succeeded: {registration_results['succeeded']}")
    log.info(f"   Failed: {registration_results['failed']}")
    
    if registration_results['failures']:
        log.warning("View registration failures:")
        for failure in registration_results['failures']:
            log.warning(f"   {failure}")
    
    log.info(f"✅ Persistent views registration complete: {registration_results['succeeded']}/{registration_results['attempted']} successful")


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
