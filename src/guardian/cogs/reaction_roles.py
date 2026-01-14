from __future__ import annotations

import asyncio
import time
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

import discord
from discord import app_commands, ui
from discord.ext import commands
import logging

from ..services.reaction_roles_store import ReactionRolesStore, ReactionRoleConfig
from ..services.panel_store import PanelStore
from ..security.permissions import admin_command
from ..utils import info_embed, error_embed, success_embed
from ..constants import COLORS

log = logging.getLogger("guardian.reaction_roles")

# Constants
REACTION_ROLES_CHANNEL = "reaction-roles"
MAX_SELECT_OPTIONS = 25
PANEL_EDIT_COOLDOWN = 1.0  # 1 second between panel edits

class AdminManagementView(ui.View):
    """Admin management UI for reaction roles."""
    
    def __init__(self, cog: 'ReactionRolesCog', interaction: discord.Interaction):
        super().__init__(timeout=1800)  # 30 minutes timeout
        self.cog = cog
        self.interaction = interaction
        self.guild_id = interaction.guild.id

    @ui.button(label="Add Roles", style=discord.ButtonStyle.primary, custom_id="guardian:v1:rr:admin:add")
    async def add_roles_button(self, interaction: discord.Interaction, button: ui.Button):
        """Open role selection to add roles."""
        await self._show_add_roles_modal(interaction)

    @ui.button(label="Remove Roles", style=discord.ButtonStyle.danger, custom_id="guardian:v1:rr:admin:remove")
    async def remove_roles_button(self, interaction: discord.Interaction, button: ui.Button):
        """Show configured roles to remove."""
        await self._show_remove_roles_select(interaction)

    @ui.button(label="Edit Roles", style=discord.ButtonStyle.secondary, custom_id="guardian:v1:rr:admin:edit")
    async def edit_roles_button(self, interaction: discord.Interaction, button: ui.Button):
        """Show configured roles to edit."""
        await self._show_edit_roles_select(interaction)

    @ui.button(label="Reorder", style=discord.ButtonStyle.secondary, custom_id="guardian:v1:rr:admin:reorder")
    async def reorder_button(self, interaction: discord.Interaction, button: ui.Button):
        """Show roles to reorder."""
        await self._show_reorder_select(interaction)

    @ui.button(label="Publish", style=discord.ButtonStyle.success, custom_id="guardian:v1:rr:admin:publish")
    async def publish_button(self, interaction: discord.Interaction, button: ui.Button):
        """Deploy/repair the member panel."""
        await self.cog.deploy_panel(interaction)

    @ui.button(label="Close", style=discord.ButtonStyle.secondary, custom_id="guardian:v1:rr:admin:close")
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        """Close the management UI."""
        await interaction.response.edit_message(content="🔐 Management panel closed.", view=None, embed=None)
        self.stop()

    async def _show_add_roles_modal(self, interaction: discord.Interaction):
        """Show role selection for adding roles."""
        roles = await self.cog._get_available_roles_for_admin(interaction.guild)
        if not roles:
            await interaction.response.send_message("❌ No available roles to add.", ephemeral=True)
            return

        # Create role select menu
        select = ui.RoleSelect(
            placeholder="Select roles to add to reaction roles...",
            max_values=min(25, len(roles))
        )
        select.options = [discord.SelectOption(
            label=role.name,
            value=str(role.id),
            description=f"Position: {role.position}"
        ) for role in roles[:25]]

        view = ui.View(timeout=180)
        view.add_item(select)

        async def select_callback(interaction: discord.Interaction):
            await self._handle_add_roles(interaction, select.values)

        select.callback = select_callback
        await interaction.response.send_message("Select roles to add:", view=view, ephemeral=True)

    async def _handle_add_roles(self, interaction: discord.Interaction, role_ids: List[str]):
        """Handle adding selected roles."""
        if not role_ids:
            await interaction.response.send_message("❌ No roles selected.", ephemeral=True)
            return

        guild = interaction.guild
        role_configs = []
        skipped = []

        for role_id in role_ids:
            role = guild.get_role(int(role_id))
            if not role:
                skipped.append(f"Role {role_id} not found")
                continue

            validation = await self.cog._validate_role(role)
            if not validation["valid"]:
                skipped.append(f"{role.name}: {validation['reason']}")
                continue

            role_configs.append({
                "role_id": role.id,
                "group_key": "games",  # Default group
                "enabled": True
            })

        if role_configs:
            errors = await self.cog.store.add_roles(guild.id, role_configs)
            if errors:
                skipped.extend(errors)

        embed = success_embed(
            f"✅ Added {len(role_configs)} roles to reaction roles."
            if role_configs else "❌ No roles were added."
        )

        if skipped:
            embed.add_field(
                name="⚠️ Skipped",
                value="\n".join(skipped[:10]) + ("..." if len(skipped) > 10 else ""),
                inline=False
            )

        await interaction.response.edit_message(embed=embed, view=None)

    async def _show_remove_roles_select(self, interaction: discord.Interaction):
        """Show configured roles for removal."""
        configured_roles = await self.cog.store.list_roles(self.guild_id)
        if not configured_roles:
            await interaction.response.send_message("❌ No configured roles to remove.", ephemeral=True)
            return

        select = ui.Select(
            placeholder="Select roles to remove from reaction roles...",
            max_values=min(25, len(configured_roles))
        )
        guild = interaction.guild
        select.options = [discord.SelectOption(
            label=f"{guild.get_role(config.role_id).name if guild.get_role(config.role_id) else 'Unknown'} ({config.group_key})",
            value=str(config.role_id),
            description=f"Group: {config.group_key} | Enabled: {'✅' if config.enabled else '❌'}"
        ) for config in configured_roles[:25]]

        view = ui.View(timeout=180)
        view.add_item(select)

        async def select_callback(interaction: discord.Interaction):
            await self._handle_remove_roles(interaction, select.values)

        select.callback = select_callback
        await interaction.response.send_message("Select roles to remove:", view=view, ephemeral=True)

    async def _handle_remove_roles(self, interaction: discord.Interaction, role_ids: List[str]):
        """Handle removing selected roles."""
        if not role_ids:
            await interaction.response.send_message("❌ No roles selected.", ephemeral=True)
            return

        role_ids_int = [int(rid) for rid in role_ids]
        errors = await self.cog.store.remove_roles(self.guild_id, role_ids_int)

        embed = success_embed(f"✅ Removed {len(role_ids_int) - len(errors)} roles from reaction roles.")
        
        if errors:
            embed.add_field(
                name="⚠️ Errors",
                value="\n".join(errors),
                inline=False
            )

        await interaction.response.edit_message(embed=embed, view=None)

    async def _show_edit_roles_select(self, interaction: discord.Interaction):
        """Show configured roles for editing."""
        configured_roles = await self.cog.store.list_roles(self.guild_id)
        if not configured_roles:
            await interaction.response.send_message("❌ No configured roles to edit.", ephemeral=True)
            return

        select = ui.Select(
            placeholder="Select a role to edit...",
            max_values=1
        )
        guild = interaction.guild
        select.options = [discord.SelectOption(
            label=f"{guild.get_role(config.role_id).name if guild.get_role(config.role_id) else 'Unknown'} ({config.group_key})",
            value=str(config.role_id),
            description=f"Group: {config.group_key} | Enabled: {'✅' if config.enabled else '❌'}"
        ) for config in configured_roles[:25]]

        view = ui.View(timeout=180)
        view.add_item(select)

        async def select_callback(interaction: discord.Interaction):
            if select.values:
                await self._show_edit_controls(interaction, int(select.values[0]))

        select.callback = select_callback
        await interaction.response.send_message("Select a role to edit:", view=view, ephemeral=True)

    async def _show_edit_controls(self, interaction: discord.Interaction, role_id: int):
        """Show edit controls for a specific role."""
        configured_roles = await self.cog.store.list_roles(self.guild_id)
        config = next((r for r in configured_roles if r.role_id == role_id), None)
        if not config:
            await interaction.response.send_message("❌ Role configuration not found.", ephemeral=True)
            return

        guild = interaction.guild
        role = guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("❌ Role not found.", ephemeral=True)
            return

        embed = info_embed(f"Editing: {role.name}")
        embed.add_field(name="Current Group", value=config.group_key)
        embed.add_field(name="Enabled", value="✅" if config.enabled else "❌")
        if config.label:
            embed.add_field(name="Label", value=config.label)
        if config.emoji:
            embed.add_field(name="Emoji", value=config.emoji)

        view = ui.View(timeout=180)
        
        # Group selection buttons
        group_select = ui.Select(
            placeholder="Change group...",
            options=[
                discord.SelectOption(label="Games", value="games"),
                discord.SelectOption(label="Interests", value="interests"),
                discord.SelectOption(label="Other", value="other")
            ]
        )
        
        async def group_callback(interaction: discord.Interaction):
            if group_select.values:
                await self.cog.store.set_group(self.guild_id, role_id, group_select.values[0])
                await interaction.response.send_message(f"✅ Group changed to {group_select.values[0]}", ephemeral=True)
        
        group_select.callback = group_callback
        view.add_item(group_select)

        # Toggle enabled button
        toggle_btn = ui.Button(
            label="Toggle Enabled" if config.enabled else "Enable Role",
            style=discord.ButtonStyle.primary
        )
        
        async def toggle_callback(interaction: discord.Interaction):
            new_state = not config.enabled
            await self.cog.store.set_enabled(self.guild_id, role_id, new_state)
            await interaction.response.send_message(
                f"✅ Role {'enabled' if new_state else 'disabled'}", 
                ephemeral=True
            )
        
        toggle_btn.callback = toggle_callback
        view.add_item(toggle_btn)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _show_reorder_select(self, interaction: discord.Interaction):
        """Show roles for reordering."""
        configured_roles = await self.cog.store.list_roles(self.guild_id)
        if not configured_roles:
            await interaction.response.send_message("❌ No configured roles to reorder.", ephemeral=True)
            return

        select = ui.Select(
            placeholder="Select a role to reorder...",
            max_values=1
        )
        guild = interaction.guild
        select.options = [discord.SelectOption(
            label=f"{guild.get_role(config.role_id).name if guild.get_role(config.role_id) else 'Unknown'}",
            value=str(config.role_id),
            description=f"Position: {config.order_index} | Group: {config.group_key}"
        ) for config in configured_roles[:25]]

        view = ui.View(timeout=180)
        view.add_item(select)

        async def select_callback(interaction: discord.Interaction):
            if select.values:
                await self._show_reorder_controls(interaction, int(select.values[0]))

        select.callback = select_callback
        await interaction.response.send_message("Select a role to reorder:", view=view, ephemeral=True)

    async def _show_reorder_controls(self, interaction: discord.Interaction, role_id: int):
        """Show reorder controls for a specific role."""
        guild = interaction.guild
        role = guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("❌ Role not found.", ephemeral=True)
            return

        embed = info_embed(f"Reordering: {role.name}")

        view = ui.View(timeout=180)
        
        up_btn = ui.Button(label="↑ Move Up", style=discord.ButtonStyle.primary, emoji="⬆️")
        down_btn = ui.Button(label="↓ Move Down", style=discord.ButtonStyle.primary, emoji="⬇️")

        async def up_callback(interaction: discord.Interaction):
            if await self.cog.store.move_role(self.guild_id, role_id, "up"):
                await interaction.response.send_message("✅ Role moved up", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Cannot move role up (already at top)", ephemeral=True)

        async def down_callback(interaction: discord.Interaction):
            if await self.cog.store.move_role(self.guild_id, role_id, "down"):
                await interaction.response.send_message("✅ Role moved down", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Cannot move role down (already at bottom)", ephemeral=True)

        up_btn.callback = up_callback
        down_btn.callback = down_btn
        
        view.add_item(up_btn)
        view.add_item(down_btn)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class MemberPanelView(ui.View):
    """Member panel for role selection."""
    
    def __init__(self, cog: 'ReactionRolesCog', guild_id: int):
        super().__init__(timeout=None)  # Persistent
        self.cog = cog
        self.guild_id = guild_id

    async def _create_group_selects(self) -> List[ui.Select]:
        """Create select menus for each role group."""
        groups = await self.cog.store.get_groups(self.guild_id)
        selects = []

        for group_key in groups:
            roles = await self.cog.store.list_group(self.guild_id, group_key)
            if not roles:
                continue

            # Handle pagination if more than 25 roles in group
            if len(roles) <= 25:
                select = ui.Select(
                    placeholder=f"Select {group_key.title()} roles...",
                    custom_id=f"guardian:v1:rr:member:{group_key}:1",
                    max_values=len(roles)
                )
                
                guild = self.cog.bot.get_guild(self.guild_id)
                for role_config in roles:
                    role = guild.get_role(role_config.role_id) if guild else None
                    label = role_config.label or (role.name if role else f"Unknown ({role_config.role_id})")
                    emoji = role_config.emoji or ""
                    
                    select.add_option(
                        label=label,
                        value=str(role_config.role_id),
                        emoji=emoji
                    )
                
                selects.append(select)
            else:
                # Paginate large groups
                for i in range(0, len(roles), 25):
                    page_roles = roles[i:i+25]
                    page_num = i // 25 + 1
                    total_pages = (len(roles) + 24) // 25
                    
                    select = ui.Select(
                        placeholder=f"{group_key.title()} ({page_num}/{total_pages})...",
                        custom_id=f"guardian:v1:rr:member:{group_key}:{page_num}",
                        max_values=len(page_roles)
                    )
                    
                    guild = self.cog.bot.get_guild(self.guild_id)
                    for role_config in page_roles:
                        role = guild.get_role(role_config.role_id) if guild else None
                        label = role_config.label or (role.name if role else f"Unknown ({role_config.role_id})")
                        emoji = role_config.emoji or ""
                        
                        select.add_option(
                            label=label,
                            value=str(role_config.role_id),
                            emoji=emoji
                        )
                    
                    selects.append(select)

        return selects

    async def refresh_view(self):
        """Refresh the view with current role configuration."""
        # Clear existing items
        self.clear_items()
        
        # Add new selects
        selects = await self._create_group_selects()
        for select in selects:
            self.add_item(select)

        # Add clear button
        clear_btn = ui.Button(
            label="Clear All Roles",
            style=discord.ButtonStyle.danger,
            custom_id="guardian:v1:rr:clear"
        )
        clear_btn.callback = self._clear_all_roles
        self.add_item(clear_btn)

    async def _clear_all_roles(self, interaction: discord.Interaction):
        """Clear all reaction roles from the member."""
        if not interaction.guild:
            return

        configured_roles = await self.cog.store.list_roles(interaction.guild.id)
        role_ids = [config.role_id for config in configured_roles if config.enabled]
        
        if not role_ids:
            await interaction.response.send_message("❌ No reaction roles configured.", ephemeral=True)
            return

        member = interaction.user
        roles_to_remove = [role for role in member.roles if role.id in role_ids]
        
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="Cleared all reaction roles")
            await interaction.response.send_message(
                f"✅ Removed {len(roles_to_remove)} reaction roles from you.", 
                ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ You don't have any reaction roles to remove.", ephemeral=True)

    async def handle_role_selection(self, interaction: discord.Interaction, select: ui.Select):
        """Handle role selection from member panel."""
        if not interaction.guild or not select.values:
            return

        member = interaction.user
        selected_role_ids = [int(rid) for rid in select.values]
        
        # Get group from custom_id
        parts = select.custom_id.split(":")
        group_key = parts[4] if len(parts) > 4 else "unknown"
        
        # Get all roles in this group
        group_roles = await self.cog.store.list_group(interaction.guild.id, group_key)
        group_role_ids = {config.role_id for config in group_roles}
        
        # Determine roles to add and remove
        current_role_ids = {role.id for role in member.roles}
        roles_to_add = []
        roles_to_remove = []
        
        for role_id in selected_role_ids:
            if role_id not in current_role_ids:
                roles_to_add.append(role_id)
        
        for role_id in group_role_ids:
            if role_id in current_role_ids and role_id not in selected_role_ids:
                roles_to_remove.append(role_id)
        
        # Apply role changes
        try:
            if roles_to_remove:
                roles_to_remove_objs = [interaction.guild.get_role(rid) for rid in roles_to_remove]
                roles_to_remove_objs = [r for r in roles_to_remove_objs if r]
                if roles_to_remove_objs:
                    await member.remove_roles(*roles_to_remove_objs, reason="Reaction role update")
            
            if roles_to_add:
                roles_to_add_objs = [interaction.guild.get_role(rid) for rid in roles_to_add]
                roles_to_add_objs = [r for r in roles_to_add_objs if r]
                if roles_to_add_objs:
                    await member.add_roles(*roles_to_add_objs, reason="Reaction role update")
            
            message = f"✅ Updated your {group_key.title()} roles."
            if roles_to_add:
                message += f" Added {len(roles_to_add)} roles."
            if roles_to_remove:
                message += f" Removed {len(roles_to_remove)} roles."
            
            await interaction.response.send_message(message, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to manage your roles.", 
                ephemeral=True
            )
        except Exception as e:
            log.error(f"Error updating roles for {member.id}: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating your roles.", 
                ephemeral=True
            )


class ReactionRolesCog(commands.Cog):
    """Future-proof reaction roles system with manual admin configuration."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = None
        self.panel_store = None
        self._panel_edit_cooldowns = {}

    async def cog_load(self):
        """Initialize stores and register persistent views."""
        # Initialize stores
        settings = self.bot.settings
        self.store = ReactionRolesStore(settings.sqlite_path)
        self.panel_store = PanelStore(settings.sqlite_path)
        
        # Initialize database schema
        await self.store.init()
        
        # Register persistent member panel view
        self.bot.add_view(MemberPanelView(self, 0))  # guild_id will be updated per message
        log.info("ReactionRolesCog loaded and persistent views registered")

    @app_commands.command(
        name="reactionroles",
        description="Reaction roles management commands"
    )
    @app_commands.describe(
        action="Choose an action: deploy, manage, list, clear_user, repair"
    )
    @admin_command()
    async def reactionroles(
        self, 
        interaction: discord.Interaction, 
        action: str
    ):
        """Main reaction roles command dispatcher."""
        await interaction.response.defer(ephemeral=True)
        
        if action == "deploy":
            await self.deploy_panel(interaction)
        elif action == "manage":
            await self.open_management_ui(interaction)
        elif action == "list":
            await self.list_configured_roles(interaction)
        elif action == "clear_user":
            await self.clear_user_roles(interaction)
        elif action == "repair":
            await self.repair_panel(interaction)
        else:
            await interaction.followup.send(
                f"❌ Unknown action: {action}. Available: deploy, manage, list, clear_user, repair",
                ephemeral=True
            )

    async def deploy_panel(self, interaction: discord.Interaction):
        """Deploy or repair the member panel."""
        if not interaction.guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        guild = interaction.guild
        
        # Check if any roles are configured
        configured_roles = await self.store.list_roles(guild.id)
        if not configured_roles:
            await interaction.followup.send(
                "❌ No roles configured yet. Use `/reactionroles manage` to add roles.",
                ephemeral=True
            )
            return

        # Find or create reaction-roles channel
        channel = discord.utils.get(guild.text_channels, name=REACTION_ROLES_CHANNEL)
        if not channel:
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=False,
                        add_reactions=False
                    )
                }
                channel = await guild.create_text_channel(
                    REACTION_ROLES_CHANNEL,
                    overwrites=overwrites,
                    reason="Reaction roles channel"
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ I don't have permission to create channels. Please create a #reaction-roles channel manually.",
                    ephemeral=True
                )
                return

        # Check cooldown for panel edits
        cooldown_key = f"{guild.id}:{channel.id}"
        now = time.time()
        if cooldown_key in self._panel_edit_cooldowns:
            if now - self._panel_edit_cooldowns[cooldown_key] < PANEL_EDIT_COOLDOWN:
                await interaction.followup.send(
                    "⚠️ Panel update in cooldown. Please wait a moment.",
                    ephemeral=True
                )
                return
        
        self._panel_edit_cooldowns[cooldown_key] = now

        try:
            # Create member panel view
            view = MemberPanelView(self, guild.id)
            await view.refresh_view()

            # Create embed
            embed = discord.Embed(
                title="🎭 Reaction Roles",
                description="Select your roles from the menus below. Roles are organized by categories for easy selection.",
                color=discord.Color.blue()
            )
            
            # Add group information
            groups = await self.store.get_groups(guild.id)
            for group_key in groups:
                group_roles = await self.store.list_group(guild.id, group_key)
                if group_roles:
                    embed.add_field(
                        name=f"{group_key.title()} ({len(group_roles)} roles)",
                        value=f"Select from the {group_key} menu below",
                        inline=True
                    )

            # Check if panel already exists
            panel = await self.panel_store.get_by_key("reaction_roles_panel")
            if panel and panel.message_id:
                try:
                    # Try to edit existing message
                    message = await channel.fetch_message(panel.message_id)
                    await message.edit(embed=embed, view=view)
                    await interaction.followup.send(
                        f"✅ Updated reaction roles panel in {channel.mention}",
                        ephemeral=True
                    )
                except discord.NotFound:
                    # Message not found, create new one
                    message = await channel.send(embed=embed, view=view)
                    await self.panel_store.upsert(
                        "reaction_roles_panel",
                        guild.id,
                        channel.id,
                        message.id
                    )
                    await interaction.followup.send(
                        f"✅ Created new reaction roles panel in {channel.mention}",
                        ephemeral=True
                    )
            else:
                # Create new panel
                message = await channel.send(embed=embed, view=view)
                await self.panel_store.upsert(
                    "reaction_roles_panel",
                    guild.id,
                    channel.id,
                    message.id
                )
                await interaction.followup.send(
                    f"✅ Created reaction roles panel in {channel.mention}",
                    ephemeral=True
                )

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to send messages in the reaction-roles channel.",
                ephemeral=True
            )
        except Exception as e:
            log.error(f"Error deploying reaction roles panel: {e}")
            await interaction.followup.send(
                "❌ An error occurred while deploying the panel. Check the logs for details.",
                ephemeral=True
            )

    async def open_management_ui(self, interaction: discord.Interaction):
        """Open the admin management UI."""
        if not interaction.guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        # Check if user has appropriate permissions
        if not interaction.user.guild_permissions.manage_roles and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(
                "❌ You need 'Manage Roles' or 'Administrator' permission to use this command.",
                ephemeral=True
            )
            return

        embed = info_embed(
            "🔧 Reaction Roles Management",
            "Use the buttons below to manage reaction roles configuration."
        )
        
        # Show current stats
        configured_roles = await self.store.list_roles(interaction.guild.id)
        enabled_count = len([r for r in configured_roles if r.enabled])
        groups = await self.store.get_groups(interaction.guild.id)
        
        embed.add_field(name="Configured Roles", value=str(len(configured_roles)))
        embed.add_field(name="Enabled Roles", value=str(enabled_count))
        embed.add_field(name="Groups", value=", ".join(groups) if groups else "None")

        view = AdminManagementView(self, interaction)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def list_configured_roles(self, interaction: discord.Interaction):
        """List all configured roles."""
        if not interaction.guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        configured_roles = await self.store.list_roles(interaction.guild.id)
        if not configured_roles:
            await interaction.followup.send("❌ No roles configured yet.", ephemeral=True)
            return

        embed = info_embed("📋 Configured Reaction Roles")
        
        # Group roles by group_key
        groups = {}
        for role_config in configured_roles:
            if role_config.group_key not in groups:
                groups[role_config.group_key] = []
            groups[role_config.group_key].append(role_config)

        for group_key, group_roles in sorted(groups.items()):
            role_list = []
            for role_config in sorted(group_roles, key=lambda x: x.order_index):
                role = interaction.guild.get_role(role_config.role_id)
                role_name = role.name if role else f"Unknown ({role_config.role_id})"
                status = "✅" if role_config.enabled else "❌"
                label = f" ({role_config.label})" if role_config.label else ""
                role_list.append(f"{status} {role_name}{label}")
            
            embed.add_field(
                name=f"{group_key.title()} ({len(group_roles)} roles)",
                value="\n".join(role_list) if role_list else "No roles",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def clear_user_roles(self, interaction: discord.Interaction):
        """Clear reaction roles from a user."""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        # For now, this will clear from the command user
        # TODO: Add target user selection
        member = interaction.user
        configured_roles = await self.store.list_roles(interaction.guild.id)
        role_ids = [config.role_id for config in configured_roles if config.enabled]
        
        if not role_ids:
            await interaction.followup.send("❌ No reaction roles configured.", ephemeral=True)
            return

        roles_to_remove = [role for role in member.roles if role.id in role_ids]
        
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="Cleared reaction roles via command")
            await interaction.followup.send(
                f"✅ Removed {len(roles_to_remove)} reaction roles from you.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ You don't have any reaction roles to remove.",
                ephemeral=True
            )

    async def repair_panel(self, interaction: discord.Interaction):
        """Repair the reaction roles panel."""
        await self.deploy_panel(interaction)

    async def _get_available_roles_for_admin(self, guild: discord.Guild) -> List[discord.Role]:
        """Get roles that can be added to reaction roles."""
        available = []
        bot_top_role = guild.me.top_role.position

        for role in guild.roles:
            if role.is_default():
                continue  # Skip @everyone
            
            if role.managed:
                continue  # Skip managed roles (bot roles, integration roles)
            
            if role.position >= bot_top_role:
                continue  # Skip roles above or equal to bot's top role
            
            # Skip protected system roles
            protected_names = ["owner", "admin", "administrator", "moderator", "mod", 
                             "support", "helper", "verified", "member", "guardian bot", "guardian services"]
            if role.name.lower() in protected_names:
                continue
            
            available.append(role)
        
        return sorted(available, key=lambda r: r.position)

    async def _validate_role(self, role: discord.Role) -> Dict[str, Any]:
        """Validate if a role can be added to reaction roles."""
        if role.is_default():
            return {"valid": False, "reason": "Cannot add @everyone"}
        
        if role.managed:
            return {"valid": False, "reason": "Cannot add managed/bot roles"}
        
        guild = role.guild
        if role.position >= guild.me.top_role.position:
            return {"valid": False, "reason": "Role is above bot's highest role"}
        
        # Check for protected role names
        protected_names = ["owner", "admin", "administrator", "moderator", "mod", 
                         "support", "helper", "verified", "member", "guardian bot", "guardian services"]
        if role.name.lower() in protected_names:
            return {"valid": False, "reason": "Protected system role"}
        
        return {"valid": True, "reason": None}

    async def cog_unload(self):
        """Clean up when cog is unloaded."""
        log.info("ReactionRolesCog unloaded")


async def setup(bot: commands.Bot):
    """Setup the reaction roles cog."""
    await bot.add_cog(ReactionRolesCog(bot))
    log.info("Reaction roles cog loaded")
