from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from ..services.panel_store import PanelStore
from ..lookup import find_text_channel
from ..services.role_config_store import RoleConfigStore
from ..permissions import require_admin


class ReactionRoleButton(discord.ui.Button):
    """Individual role button for reaction roles UI."""
    
    def __init__(self, role_name: str, emoji: str, role_id: int):
        self.role_name = role_name
        self.role_id = role_id
        super().__init__(
            label=role_name,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"reaction_role:{role_id}"
        )
    
    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle role toggle with stateless logic."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        
        guild = interaction.guild
        member = interaction.user
        role = guild.get_role(self.role_id)
        
        if not role:
            await interaction.response.send_message(
                "❌ Role not found. Contact server admin.",
                ephemeral=True
            )
            return
        
        try:
            if role in member.roles:
                # Remove role
                await member.remove_roles(role, reason="Reaction role toggle")
                await interaction.response.send_message(
                    f"❌ Removed {self.role_name} role",
                    ephemeral=True
                )
            else:
                # Add role
                await member.add_roles(role, reason="Reaction role toggle")
                await interaction.response.send_message(
                    f"✅ Added {self.role_name} role",
                    ephemeral=True
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing permissions to manage roles.",
                ephemeral=True
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ API error updating roles.",
                ephemeral=True
            )


class ReactionRolesView(discord.ui.View):
    """Persistent reaction roles view with multiple buttons like verify UI."""
    
    def __init__(self, guild_id: int, role_configs: list):
        super().__init__(timeout=None)  # Persistent view
        self.guild_id = guild_id
        
        # Add role buttons
        for config in role_configs:
            self.add_item(ReactionRoleButton(
                config.label,
                config.emoji or "🎯",
                config.role_id
            ))


class PersistentRoleSelect(discord.ui.Select):
    """Persistent role selection dropdown."""
    
    def __init__(self, guild_id: int, role_configs: list, max_values: int = 25):
        self.guild_id = guild_id
        self.role_configs = {str(config.role_id): config for config in role_configs}
        
        options = [
            discord.SelectOption(
                label=config.label,
                value=str(config.role_id),
                emoji=config.emoji
            )
            for config in role_configs[:25]  # Discord limit
        ]
        
        super().__init__(
            placeholder="Select roles to assign...",
            min_values=0,
            max_values=max_values,
            options=options,
            custom_id=f"persistent_role_select:{guild_id}"
        )
    
    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle role selection with stateless logic."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        
        member = interaction.user
        selected_role_ids = set(int(v) for v in self.values)
        available_role_ids = set(int(config.role_id) for config in self.role_configs.values())
        
        to_add = []
        to_remove = []
        
        # Determine which roles to add/remove
        for role_id in available_role_ids:
            role = interaction.guild.get_role(role_id)
            if not role:
                continue
                
            if role_id in selected_role_ids and role not in member.roles:
                to_add.append(role)
            elif role_id not in selected_role_ids and role in member.roles:
                to_remove.append(role)
        
        # Apply role changes
        try:
            if to_remove:
                await member.remove_roles(*to_remove, reason="Role selection panel update")
            if to_add:
                await member.add_roles(*to_add, reason="Role selection panel update")
            
            await interaction.response.send_message(
                f"✅ Roles updated: +{len(to_add)} -{len(to_remove)}", 
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing permissions to manage roles.", 
                ephemeral=True
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ API error updating roles.", 
                ephemeral=True
            )


class PersistentRoleView(discord.ui.View):
    """Persistent role selection view that survives bot restarts."""
    
    def __init__(self, guild_id: int, role_configs: list):
        super().__init__(timeout=None)  # Persistent view
        self.guild_id = guild_id
        self.role_configs = role_configs
        
        # Add role selection dropdown
        self.add_item(PersistentRoleSelect(guild_id, role_configs))


class RolePanelCog(commands.Cog):
    """Cog for managing persistent role selection panels."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.panel_store: Optional[PanelStore] = None
        self.role_config_store: Optional[RoleConfigStore] = None
    
    async def cog_load(self) -> None:
        """Initialize stores and register persistent views."""
        # Use bot's stores
        self.panel_store = self.bot.panel_store
        self.role_config_store = self.bot.role_config_store
        
        # Register persistent views for all existing panels
        await self._restore_panels()
    
    async def _restore_panels(self) -> None:
        """Restore all persistent role panels on startup."""
        if not self.panel_store:
            return
            
        panels = await self.panel_store.list_all_panels()
        for panel in panels:
            if panel.panel_key.startswith('role_panel_') or panel.panel_key.startswith('reaction_roles_'):
                try:
                    # Get role configurations for this guild
                    role_configs = await self.role_config_store.list_roles(panel.guild_id)
                    
                    # Create and register view (button-based for reaction roles)
                    if 'reaction_roles' in panel.panel_key:
                        view = ReactionRolesView(panel.guild_id, role_configs)
                    else:
                        view = PersistentRoleView(panel.guild_id, role_configs)
                    
                    self.bot.add_view(view, message_id=panel.message_id)
                    
                    self.bot.logger.info(f"✅ Restored role panel {panel.panel_key} in guild {panel.guild_id}")
                except Exception as e:
                    self.bot.logger.exception(f"❌ Failed to restore role panel {panel.panel_key} in guild {panel.guild_id}: {e}")
    
    @app_commands.command(name="rolepanel", description="Deploy role selection panel")
    @require_admin()
    async def rolepanel(self, interaction: discord.Interaction) -> None:
        """Deploy role selection panel."""
        await self._deploy_role_panel(interaction)
    
    async def _deploy_role_panel(self, interaction: discord.Interaction) -> None:
        """Deploy a persistent role selection panel."""
        if not self.role_config_store or not self.panel_store:
            await interaction.response.send_message("Stores not initialized.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        
        # Get configured roles
        role_configs = await self.role_config_store.list_roles(guild.id)
        if not role_configs:
            await interaction.followup.send(
                "❌ No roles configured. Use `/roleselect add` first.",
                ephemeral=True
            )
            return
        
        # Find or create role panel channel
        channel = find_text_channel(guild, "choose-your-games") or find_text_channel(guild, "server-info")
        if not channel:
            try:
                channel = await guild.create_text_channel(
                    "roles", 
                    reason="Role selection panel channel"
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ Missing permissions to create channels.",
                    ephemeral=True
                )
                return
        
        # Create panel embed
        embed = discord.Embed(
            title="🎭 Role Selection",
            description="Select your roles from the dropdown below. You can change them anytime!",
            color=discord.Color.blue()
        )
        
        # Group roles by category
        role_groups = {}
        for config in role_configs:
            group = config.group or "Other"
            if group not in role_groups:
                role_groups[group] = []
            role_groups[group].append(config)
        
        # Add role groups to embed
        for group, configs in role_groups.items():
            role_text = "\n".join(
                f"{config.emoji or '•'} {config.label}" 
                for config in configs[:10]  # Limit display
            )
            embed.add_field(name=group, value=role_text, inline=True)
        
        # Create and send view
        view = PersistentRoleView(guild.id, role_configs)
        message = await channel.send(embed=embed, view=view)
        
        # Store panel reference
        panel_key = f"role_panel_main"
        await self.panel_store.upsert_panel(
            panel_key, guild.id, channel.id, message.id
        )
        
        await interaction.followup.send(
            f"✅ Role panel deployed: {message.jump_url}",
            ephemeral=True
        )
    
    async def _deploy_role_panel_for_overhaul(self, guild: discord.Guild, channel: discord.TextChannel) -> None:
        """Deploy role panel specifically for overhaul (bypass channel creation)."""
        if not self.role_config_store or not self.panel_store:
            return
        
        # Get configured roles
        role_configs = await self.role_config_store.list_roles(guild.id)
        if not role_configs:
            return
        
        # Create panel embed
        embed = discord.Embed(
            title="🎯 Choose Your Roles",
            description="Click buttons below to toggle roles on/off. You can change them anytime!",
            color=discord.Color.blue()
        )
        
        # Group roles by category
        role_groups = {}
        for config in role_configs:
            group = config.group or "Other"
            if group not in role_groups:
                role_groups[group] = []
            role_groups[group].append(config)
        
        # Add role groups to embed
        for group, configs in role_groups.items():
            role_text = "\n".join(
                f"{config.emoji or '•'} {config.label}" 
                for config in configs[:10]  # Limit display
            )
            embed.add_field(name=group, value=role_text, inline=True)
        
        # Create and send button-based view (like verify UI)
        view = ReactionRolesView(guild.id, role_configs)
        message = await channel.send(embed=embed, view=view)
        
        # Store panel reference
        panel_key = f"reaction_roles_main"
        await self.panel_store.upsert_panel(
            panel_key, guild.id, channel.id, message.id
        )


class RoleSelectCog(commands.Cog):
    """Cog for managing role selection configuration."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.role_config_store: Optional[RoleConfigStore] = None
    
    async def cog_load(self) -> None:
        """Initialize role config store."""
        # Use bot's store
        self.role_config_store = self.bot.role_config_store
    
    roleselect = app_commands.Group(name="roleselect", description="Manage role selection configuration")

    @roleselect.command(name="add", description="Add a role to selection panel")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        role="Role to add",
        label="Display label for the role",
        emoji="Emoji for the role (optional)",
        group="Group/category for the role (optional)"
    )
    async def roleselect_add(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        label: str,
        emoji: Optional[str] = None,
        group: Optional[str] = None
    ) -> None:
        """Add a role to the selection panel."""
        
        if not self.role_config_store:
            await interaction.response.send_message("Store not initialized.", ephemeral=True)
            return
        
        # Clean emoji input
        if emoji and len(emoji) > 2:
            emoji = None
        
        await self.role_config_store.upsert_role(
            interaction.guild.id, role.id, label, emoji, group
        )
        
        await interaction.response.send_message(
            f"✅ Added role '{label}' to selection panel.",
            ephemeral=True
        )
    
    @roleselect.command(name="remove", description="Remove a role from selection panel")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(role="Role to remove")
    async def roleselect_remove(
        self,
        interaction: discord.Interaction,
        role: discord.Role
    ) -> None:
        """Remove a role from the selection panel."""
        
        if not self.role_config_store:
            await interaction.response.send_message("Store not initialized.", ephemeral=True)
            return
        
        await self.role_config_store.delete_role(interaction.guild.id, role.id)
        
        await interaction.response.send_message(
            f"✅ Removed role '{role.name}' from selection panel.",
            ephemeral=True
        )
    
    @roleselect.command(name="list", description="List configured roles")
    @app_commands.checks.has_permissions(administrator=True)
    async def roleselect_list(self, interaction: discord.Interaction) -> None:
        """List all configured roles."""
        
        if not self.role_config_store:
            await interaction.response.send_message("Store not initialized.", ephemeral=True)
            return
        
        role_configs = await self.role_config_store.list_roles(interaction.guild.id)
        if not role_configs:
            await interaction.response.send_message(
                "No roles configured for selection panel.",
                ephemeral=True
            )
            return
        
        # Group roles for display
        role_groups = {}
        for config in role_configs:
            group = config.group or "Other"
            if group not in role_groups:
                role_groups[group] = []
            role_groups[group].append(config)
        
        embed = discord.Embed(
            title="🎭 Role Selection Configuration",
            color=discord.Color.blue()
        )
        
        for group, configs in role_groups.items():
            role_text = "\n".join(
                f"{config.emoji or '•'} {config.label} (<@&{config.role_id}>)"
                for config in configs
            )
            embed.add_field(name=group, value=role_text, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


# Setup function for adding cogs
async def setup(bot: commands.Bot) -> None:
    """Add the role panel and role selection cogs to the bot."""
    await bot.add_cog(RolePanelCog(bot))
    await bot.add_cog(RoleSelectCog(bot))
