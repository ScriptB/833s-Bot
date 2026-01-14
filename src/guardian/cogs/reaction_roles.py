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


class StreamlinedAdminView(ui.View):
    """Streamlined admin management UI for reaction roles."""
    
    def __init__(self, cog: 'ReactionRolesCog'):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.cog = cog
        self.message = None

    async def on_timeout(self) -> None:
        """Handle view timeout."""
        if self.message:
            try:
                await self.message.edit(content="🔐 Management panel timed out.", view=None, embed=None)
            except:
                pass

    @ui.button(label="➕ Add Roles", style=discord.ButtonStyle.primary, custom_id="rr_add", row=0)
    async def add_roles(self, interaction: discord.Interaction, button: ui.Button):
        """Add roles to reaction roles system."""
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        available_roles = await self.cog._get_available_roles_for_admin(guild)
        
        if not available_roles:
            await interaction.followup.send("❌ No available roles to add.", ephemeral=True)
            return

        # Create select menu
        select = ui.RoleSelect(
            placeholder="Select roles to add...",
            max_values=min(25, len(available_roles))
        )
        
        for role in available_roles[:25]:
            select.add_option(
                label=role.name,
                value=str(role.id),
                description=f"Position: {role.position}"
            )

        view = ui.View(timeout=60)
        view.add_item(select)

        async def select_callback(select_interaction: discord.Interaction):
            await select_interaction.response.defer(ephemeral=True)
            
            if not select.values:
                await select_interaction.followup.send("❌ No roles selected.", ephemeral=True)
                return

            # Process roles
            added = []
            skipped = []
            
            for role_id in select.values:
                role = guild.get_role(int(role_id))
                if not role:
                    skipped.append(f"Role {role_id} not found")
                    continue

                validation = await self.cog._validate_role(role)
                if not validation["valid"]:
                    skipped.append(f"{role.name}: {validation['reason']}")
                    continue

                # Add to database
                errors = await self.cog.store.add_roles(guild.id, [{
                    "role_id": role.id,
                    "group_key": "games",
                    "enabled": True
                }])
                
                if errors:
                    skipped.append(f"{role.name}: Database error")
                else:
                    added.append(role.name)

            # Send result
            embed = success_embed(f"✅ Added {len(added)} roles to reaction roles.")
            
            if added:
                embed.add_field(name="Added Roles", value="\n".join(added[:10]), inline=False)
                if len(added) > 10:
                    embed.add_field(name="More", value=f"...and {len(added) - 10} more", inline=False)
            
            if skipped:
                embed.add_field(name="⚠️ Skipped", value="\n".join(skipped[:5]), inline=False)
                if len(skipped) > 5:
                    embed.add_field(name="More Skipped", value=f"...and {len(skipped) - 5} more", inline=False)

            await select_interaction.followup.send(embed=embed, ephemeral=True)

        select.callback = select_callback
        await interaction.followup.send("Select roles to add:", view=view, ephemeral=True)

    @ui.button(label="➖ Remove Roles", style=discord.ButtonStyle.danger, custom_id="rr_remove", row=0)
    async def remove_roles(self, interaction: discord.Interaction, button: ui.Button):
        """Remove roles from reaction roles system."""
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        configured_roles = await self.cog.store.list_roles(guild.id)
        
        if not configured_roles:
            await interaction.followup.send("❌ No roles configured to remove.", ephemeral=True)
            return

        # Create select menu
        select = ui.Select(
            placeholder="Select roles to remove...",
            max_values=min(25, len(configured_roles))
        )
        
        for role_config in configured_roles[:25]:
            role = guild.get_role(role_config.role_id)
            role_name = role.name if role else f"Unknown ({role_config.role_id})"
            
            select.add_option(
                label=f"{role_name} ({role_config.group_key})",
                value=str(role_config.role_id),
                description=f"Group: {role_config.group_key}"
            )

        view = ui.View(timeout=60)
        view.add_item(select)

        async def select_callback(select_interaction: discord.Interaction):
            await select_interaction.response.defer(ephemeral=True)
            
            if not select.values:
                await select_interaction.followup.send("❌ No roles selected.", ephemeral=True)
                return

            # Remove roles
            role_ids = [int(rid) for rid in select.values]
            errors = await self.cog.store.remove_roles(guild.id, role_ids)
            
            removed = len(role_ids) - len(errors)
            
            embed = success_embed(f"✅ Removed {removed} roles from reaction roles.")
            
            if errors:
                embed.add_field(name="⚠️ Errors", value="\n".join(errors), inline=False)

            await select_interaction.followup.send(embed=embed, ephemeral=True)

        select.callback = select_callback
        await interaction.followup.send("Select roles to remove:", view=view, ephemeral=True)

    @ui.button(label="📋 List Roles", style=discord.ButtonStyle.secondary, custom_id="rr_list", row=1)
    async def list_roles(self, interaction: discord.Interaction, button: ui.Button):
        """List all configured roles."""
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        configured_roles = await self.cog.store.list_roles(guild.id)
        
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
                role = guild.get_role(role_config.role_id)
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

    @ui.button(label="🚀 Deploy Panel", style=discord.ButtonStyle.success, custom_id="rr_deploy", row=1)
    async def deploy_panel(self, interaction: discord.Interaction, button: ui.Button):
        """Deploy member panel."""
        await interaction.response.defer(ephemeral=True)
        await self.cog.deploy_panel(interaction)

    @ui.button(label="❌ Close", style=discord.ButtonStyle.secondary, custom_id="rr_close", row=1)
    async def close(self, interaction: discord.Interaction, button: ui.Button):
        """Close management UI."""
        await interaction.response.edit_message(content="🔐 Management panel closed.", view=None, embed=None)
        self.stop()


class StreamlinedMemberView(ui.View):
    """Streamlined member panel for role selection."""
    
    def __init__(self, cog: 'ReactionRolesCog', guild_id: int):
        super().__init__(timeout=None)  # Persistent
        self.cog = cog
        self.guild_id = guild_id

    async def _refresh_view(self):
        """Refresh view with current role configuration."""
        self.clear_items()
        
        # Get all configured roles
        configured_roles = await self.cog.store.list_roles(self.guild_id)
        if not configured_roles:
            return

        # Group roles by group
        groups = {}
        for role_config in configured_roles:
            if not role_config.enabled:
                continue
            if role_config.group_key not in groups:
                groups[role_config.group_key] = []
            groups[role_config.group_key].append(role_config)

        # Create select menus for each group
        guild = self.cog.bot.get_guild(self.guild_id)
        for group_key, group_roles in sorted(groups.items()):
            if len(group_roles) <= 25:
                select = ui.Select(
                    placeholder=f"Select {group_key.title()} roles...",
                    custom_id=f"rr_member_{group_key}",
                    max_values=len(group_roles)
                )
                
                for role_config in group_roles:
                    role = guild.get_role(role_config.role_id) if guild else None
                    label = role_config.label or (role.name if role else f"Unknown ({role_config.role_id})")
                    emoji = role_config.emoji or ""
                    
                    select.add_option(
                        label=label,
                        value=str(role_config.role_id),
                        emoji=emoji
                    )
                
                select.callback = self._create_role_callback(group_key)
                self.add_item(select)

        # Add clear button if any roles exist
        if configured_roles:
            clear_btn = ui.Button(
                label="Clear All Roles",
                style=discord.ButtonStyle.danger,
                custom_id="rr_clear_all"
            )
            clear_btn.callback = self._clear_all_roles
            self.add_item(clear_btn)

    def _create_role_callback(self, group_key: str):
        """Create a role selection callback for a group."""
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            
            if not interaction.guild or not interaction.data.get('values'):
                return

            member = interaction.user
            selected_role_ids = [int(rid) for rid in interaction.data['values']]
            
            # Get all roles in this group
            group_roles = await self.cog.store.list_group(interaction.guild.id, group_key)
            group_role_ids = {config.role_id for config in group_roles}
            
            # Determine roles to add and remove
            current_role_ids = {role.id for role in member.roles}
            roles_to_add = [rid for rid in selected_role_ids if rid not in current_role_ids]
            roles_to_remove = [rid for rid in group_role_ids if rid in current_role_ids and rid not in selected_role_ids]
            
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
                
                await interaction.followup.send(message, ephemeral=True)
                
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ I don't have permission to manage your roles.", 
                    ephemeral=True
                )
            except Exception as e:
                log.error(f"Error updating roles for {member.id}: {e}")
                await interaction.followup.send(
                    "❌ An error occurred while updating your roles.", 
                    ephemeral=True
                )
        
        return callback

    async def _clear_all_roles(self, interaction: discord.Interaction):
        """Clear all reaction roles from member."""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            return

        configured_roles = await self.cog.store.list_roles(interaction.guild.id)
        role_ids = [config.role_id for config in configured_roles if config.enabled]
        
        if not role_ids:
            await interaction.followup.send("❌ No reaction roles configured.", ephemeral=True)
            return

        member = interaction.user
        roles_to_remove = [role for role in member.roles if role.id in role_ids]
        
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="Cleared all reaction roles")
            await interaction.followup.send(
                f"✅ Removed {len(roles_to_remove)} reaction roles from you.", 
                ephemeral=True
            )
        else:
            await interaction.followup.send("❌ You don't have any reaction roles to remove.", ephemeral=True)


class ReactionRolesCog(commands.Cog):
    """Streamlined reaction roles system with manual admin configuration."""
    
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
        
        log.info("ReactionRolesCog loaded and stores initialized")

    @app_commands.command(
        name="reactionroles",
        description="Reaction roles management commands"
    )
    @app_commands.describe(
        action="Choose an action: manage, deploy, list, clear"
    )
    @admin_command()
    async def reactionroles(
        self, 
        interaction: discord.Interaction, 
        action: str
    ):
        """Main reaction roles command dispatcher."""
        await interaction.response.defer(ephemeral=True)
        
        if action == "manage":
            await self.open_management_ui(interaction)
        elif action == "deploy":
            await self.deploy_panel(interaction)
        elif action == "list":
            await self.list_configured_roles(interaction)
        elif action == "clear":
            await self.clear_user_roles(interaction)
        else:
            await interaction.followup.send(
                f"❌ Unknown action: {action}. Available: manage, deploy, list, clear",
                ephemeral=True
            )

    async def open_management_ui(self, interaction: discord.Interaction):
        """Open streamlined admin management UI."""
        if not interaction.guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        # Check permissions
        if not interaction.user.guild_permissions.manage_roles and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(
                "❌ You need 'Manage Roles' or 'Administrator' permission to use this command.",
                ephemeral=True
            )
            return

        # Get stats
        configured_roles = await self.store.list_roles(interaction.guild.id)
        enabled_count = len([r for r in configured_roles if r.enabled])
        groups = await self.store.get_groups(interaction.guild.id)
        
        # Create embed
        embed = info_embed("🔧 Reaction Roles Management")
        embed.description = "Use the buttons below to manage reaction roles configuration."
        
        embed.add_field(name="Configured Roles", value=str(len(configured_roles)))
        embed.add_field(name="Enabled Roles", value=str(enabled_count))
        embed.add_field(name="Groups", value=", ".join(groups) if groups else "None")

        # Create and send view
        view = StreamlinedAdminView(self)
        message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        view.message = message

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

        # Check cooldown
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
            view = StreamlinedMemberView(self, guild.id)
            await view._refresh_view()

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
        """Clear reaction roles from the command user."""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

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
