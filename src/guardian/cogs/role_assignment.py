from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from guardian.services.api_wrapper import safe_add_role, safe_remove_role
from guardian.security.permissions import user_command
from guardian.constants import COLORS

log = logging.getLogger("guardian.role_assignment")


@dataclass
class RoleCategory:
    """Category of assignable roles."""
    name: str
    display_name: str
    description: str
    emoji: str
    roles: List[Dict[str, Any]]  # Each dict has: name, emoji, description


class RoleSelectView(discord.ui.View):
    """View containing role selection dropdowns."""
    
    def __init__(self, role_cog: 'RoleAssignmentCog'):
        super().__init__(timeout=None)  # Persistent view
        self.role_cog = role_cog
        
        # Add select menus for each category
        for category in role_cog.role_categories:
            self.add_item(RoleSelectMenu(category, role_cog))


class RoleSelectMenu(discord.ui.Select):
    """Select menu for a role category."""
    
    def __init__(self, category: RoleCategory, role_cog: 'RoleAssignmentCog'):
        self.category = category
        self.role_cog = role_cog
        
        # Create options
        options = []
        for role_info in category.roles:
            options.append(
                discord.SelectOption(
                    label=role_info["name"],
                    description=role_info.get("description", ""),
                    emoji=role_info.get("emoji"),
                    value=f"{category.name}:{role_info['name']}"
                )
            )
        
        super().__init__(
            placeholder=f"Select {category.display_name}...",
            min_values=0,
            max_values=len(options),
            options=options,
            custom_id=f"guardian_roles_{category.name}"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle role selection."""
        await self.role_cog.handle_role_selection(interaction, self.category, self.values)


class RoleAssignmentCog(commands.Cog):
    """Commercial-grade role assignment system with select menus."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.role_categories = self._define_role_categories()
    
    def _define_role_categories(self) -> List[RoleCategory]:
        """Define the available role categories."""
        return [
            RoleCategory(
                name="games",
                display_name="Game Roles",
                description="Get access to game-specific channels",
                emoji="🎮",
                roles=[
                    {"name": "Roblox", "emoji": "🟥", "description": "Access to ROBLOX channels"},
                    {"name": "Minecraft", "emoji": "🟩", "description": "Access to MINECRAFT channels"},
                    {"name": "ARK", "emoji": "🟧", "description": "Access to ARK channels"},
                    {"name": "FPS", "emoji": "🔴", "description": "Access to FPS channels"}
                ]
            ),
            RoleCategory(
                name="interests",
                display_name="Interest Roles",
                description="Get access to interest-specific channels",
                emoji="🎯",
                roles=[
                    {"name": "Coding", "emoji": "💻", "description": "Access to CODING channels"},
                    {"name": "Snakes", "emoji": "🐍", "description": "Access to SNAKES channels"}
                ]
            )
        ]
    
    async def cog_load(self):
        """Register persistent views when cog loads."""
        self.bot.add_view(RoleSelectView(self))
        log.info("Role assignment views registered")
    
    async def handle_role_selection(self, interaction: discord.Interaction, category: RoleCategory, selected_values: List[str]):
        """Handle role selection changes."""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send("❌ This can only be used in a server.", ephemeral=True)
            return
        
        member = interaction.user
        
        # Get current roles for this category
        current_role_names = set()
        for role in member.roles:
            if self._is_role_in_category(role.name, category):
                current_role_names.add(role.name)
        
        # Determine roles to add and remove
        selected_role_names = set()
        for value in selected_values:
            parts = value.split(":", 1)
            if len(parts) == 2:
                selected_role_names.add(parts[1])
        
        roles_to_add = selected_role_names - current_role_names
        roles_to_remove = current_role_names - selected_role_names
        
        # Apply role changes
        added_roles = []
        removed_roles = []
        errors = []
        
        # Add roles
        for role_name in roles_to_add:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role:
                result = await safe_add_role(member, role, reason="User selected via role menu")
                if result.success:
                    added_roles.append(role_name)
                else:
                    errors.append(f"Failed to add {role_name}")
            else:
                errors.append(f"Role {role_name} not found")
        
        # Remove roles
        for role_name in roles_to_remove:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role:
                result = await safe_remove_role(member, role, reason="User deselected via role menu")
                if result.success:
                    removed_roles.append(role_name)
                else:
                    errors.append(f"Failed to remove {role_name}")
            else:
                errors.append(f"Role {role_name} not found")
        
        # Create response embed
        embed = discord.Embed(
            title="🎯 Roles Updated",
            color=COLORS["primary"]
        )
        
        if added_roles:
            embed.add_field(
                name="✅ Added Roles",
                value=", ".join(f"**{name}**" for name in added_roles),
                inline=False
            )
        
        if removed_roles:
            embed.add_field(
                name="❌ Removed Roles",
                value=", ".join(f"**{name}**" for name in removed_roles),
                inline=False
            )
        
        if errors:
            embed.add_field(
                name="⚠️ Errors",
                value="\n".join(errors),
                inline=False
            )
        
        if not added_roles and not removed_roles:
            embed.description = "No changes were made to your roles."
        else:
            embed.description = "Your roles have been updated successfully!"
        
        embed.set_footer(text="Changes may take a moment to take effect.")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Log the changes
        log.info(
            f"Role selection updated for {member.id} in {interaction.guild.id}: "
            f"added={added_roles}, removed={removed_roles}, errors={len(errors)}"
        )
    
    def _is_role_in_category(self, role_name: str, category: RoleCategory) -> bool:
        """Check if a role belongs to a category."""
        return any(role_info["name"] == role_name for role_info in category.roles)
    
    async def deploy_role_panel(self, guild: discord.Guild) -> Optional[discord.Message]:
        """Deploy the role assignment panel."""
        channel = discord.utils.get(guild.text_channels, name="reaction-roles")
        if not channel:
            log.warning(f"reaction-roles channel not found in guild {guild.id}")
            return None
        
        embed = discord.Embed(
            title="🎯 Choose Your Roles",
            description=(
                "Select roles below to get access to specific channels and features!\n\n"
                "**🎮 Game Roles:**\n"
                "Get access to game-specific channels and discussions\n\n"
                "**🎯 Interest Roles:**\n"
                "Get access to interest-specific channels and communities\n\n"
                "You can change your selections at any time."
            ),
            color=COLORS["primary"]
        )
        
        # Add category information
        for category in self.role_categories:
            role_list = []
            for role_info in category.roles:
                role_list.append(f"{role_info.get('emoji', '•')} {role_info['name']}")
            
            embed.add_field(
                name=f"{category.emoji} {category.display_name}",
                value=f"{category.description}\n\n{', '.join(role_list)}",
                inline=False
            )
        
        embed.add_field(
            name="📝 Important Notes",
            value=(
                "• You can select multiple roles\n"
                "• Changes take effect immediately\n"
                "• Staff roles are not assignable here\n"
                "• Contact staff if you need help"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use the dropdown menus below to select your roles")
        
        view = RoleSelectView(self)
        
        try:
            message = await channel.send(embed=embed, view=view)
            log.info(f"Deployed role panel in guild {guild.id}")
            return message
        except discord.Forbidden:
            log.error(f"No permission to send messages in reaction-roles channel in guild {guild.id}")
            return None
        except Exception as e:
            log.exception(f"Error deploying role panel in guild {guild.id}: {e}")
            return None
    
    @app_commands.command(
        name="roles",
        description="Open the role selection menu"
    )
    @user_command()
    async def roles_command(self, interaction: discord.Interaction):
        """Slash command to open role selection."""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send("❌ This can only be used in a server.", ephemeral=True)
            return
        
        # Create a temporary view for this interaction
        view = discord.ui.View(timeout=180)  # 3 minutes timeout
        
        for category in self.role_categories:
            # Create options for this category
            options = []
            for role_info in category.roles:
                options.append(
                    discord.SelectOption(
                        label=role_info["name"],
                        description=role_info.get("description", ""),
                        emoji=role_info.get("emoji"),
                        value=f"{category.name}:{role_info['name']}"
                    )
                )
            
            select = discord.ui.Select(
                placeholder=f"Select {category.display_name}...",
                min_values=0,
                max_values=len(options),
                options=options
            )
            
            async def select_callback(interaction: discord.Interaction, cat=category, sel=select):
                await self.handle_role_selection(interaction, cat, sel.values)
            
            select.callback = select_callback
            view.add_item(select)
        
        embed = discord.Embed(
            title="🎯 Role Selection",
            description="Select the roles you want to have access to:",
            color=COLORS["primary"]
        )
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(
        name="myroles",
        description="Show your current roles"
    )
    @user_command()
    async def myroles_command(self, interaction: discord.Interaction):
        """Show user's current assignable roles."""
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send("❌ This can only be used in a server.", ephemeral=True)
            return
        
        member = interaction.user
        
        embed = discord.Embed(
            title="🎯 Your Current Roles",
            color=COLORS["primary"]
        )
        
        has_roles = False
        
        for category in self.role_categories:
            current_roles = []
            for role_info in category.roles:
                if any(role.name == role_info["name"] for role in member.roles):
                    current_roles.append(f"{role_info.get('emoji', '•')} {role_info['name']}")
            
            if current_roles:
                has_roles = True
                embed.add_field(
                    name=f"{category.emoji} {category.display_name}",
                    value=", ".join(current_roles),
                    inline=False
                )
        
        if not has_roles:
            embed.description = "You don't have any assignable roles yet. Use `/roles` to select some!"
        else:
            embed.description = "Here are your current assignable roles. Use `/roles` to change them."
        
        embed.set_footer(text="Staff roles and system roles are not shown here.")
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Setup function for the cog."""
    await bot.add_cog(RoleAssignmentCog(bot))
