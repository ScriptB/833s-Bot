from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps

import discord

from ..utils import find_role_fuzzy

log = logging.getLogger("guardian.permissions")


class PermissionError(Exception):
    """Raised when permission requirements are not met."""
    
    def __init__(self, message: str, missing_permissions: list[str], fix_instructions: str):
        super().__init__(message)
        self.missing_permissions = missing_permissions
        self.fix_instructions = fix_instructions


def require_guild_permission(permission: str):
    """Decorator to require a specific guild permission."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            if not interaction.guild:
                await interaction.response.send_message(
                    "❌ This command can only be used in a server.",
                    ephemeral=True
                )
                return
            
            # Check if user has the required permission
            if not getattr(interaction.user.guild_permissions, permission, False):
                perm_name = permission.replace("_", " ").title()
                
                embed = discord.Embed(
                    title="❌ Permission Required",
                    description=f"You need the **{perm_name}** permission to use this command.",
                    color=discord.Color.red()
                )
                
                embed.add_field(
                    name="🔧 How to Fix",
                    value=(
                        "1. Ask a server administrator to grant you this permission\n"
                        "2. Or have an admin run this command instead"
                    ),
                    inline=False
                )
                
                embed.set_footer(text="This is a security measure to protect server management.")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            return await func(self, interaction, *args, **kwargs)
        
        return wrapper
    return decorator


def require_any_permission(*permissions: str):
    """Decorator to require any of the specified permissions."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            if not interaction.guild:
                await interaction.response.send_message(
                    "❌ This command can only be used in a server.",
                    ephemeral=True
                )
                return
            
            # Check if user has any of the required permissions
            has_permission = any(
                getattr(interaction.user.guild_permissions, perm, False) 
                for perm in permissions
            )
            
            if not has_permission:
                perm_names = [perm.replace("_", " ").title() for perm in permissions]
                perms_text = " or ".join(perm_names)
                
                embed = discord.Embed(
                    title="❌ Permission Required",
                    description=f"You need one of these permissions: **{perms_text}**",
                    color=discord.Color.red()
                )
                
                embed.add_field(
                    name="🔧 How to Fix",
                    value=(
                        "1. Ask a server administrator to grant you one of these permissions\n"
                        "2. Or have an admin run this command instead"
                    ),
                    inline=False
                )
                
                embed.set_footer(text="This is a security measure to protect server management.")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            return await func(self, interaction, *args, **kwargs)
        
        return wrapper
    return decorator


def require_bot_permission(permission: str):
    """Decorator to ensure bot has a specific permission."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            if not interaction.guild:
                await interaction.response.send_message(
                    "❌ This command can only be used in a server.",
                    ephemeral=True
                )
                return
            
            # Check if bot has the required permission
            if not getattr(interaction.guild.me.guild_permissions, permission, False):
                perm_name = permission.replace("_", " ").title()
                
                embed = discord.Embed(
                    title="❌ Bot Permission Missing",
                    description=f"The bot needs the **{perm_name}** permission to perform this action.",
                    color=discord.Color.orange()
                )
                
                embed.add_field(
                    name="🔧 How to Fix",
                    value=(
                        f"1. Go to Server Settings > Roles\n"
                        f"2. Find the bot's role\n"
                        f"3. Enable the **{perm_name}** permission\n"
                        f"4. Make sure the bot's role is above the roles it needs to manage"
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="⚠️ Important",
                    value="The bot's role must be higher than roles it needs to manage in the role hierarchy.",
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            return await func(self, interaction, *args, **kwargs)
        
        return wrapper
    return decorator


def require_bot_role_above(target_role_name: str = None):
    """Decorator to ensure bot's role is above a specific role or all user roles."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            if not interaction.guild:
                await interaction.response.send_message(
                    "❌ This command can only be used in a server.",
                    ephemeral=True
                )
                return
            
            bot_role = interaction.guild.me.top_role
            
            if target_role_name:
                # Check against specific role
                target_role = find_role_fuzzy(interaction.guild, target_role_name)
                if target_role and bot_role.position <= target_role.position:
                    embed = discord.Embed(
                        title="❌ Bot Role Position Issue",
                        description=f"The bot's role must be above the **{target_role_name}** role.",
                        color=discord.Color.orange()
                    )
                    
                    embed.add_field(
                        name="🔧 How to Fix",
                        value=(
                            f"1. Go to Server Settings > Roles\n"
                            f"2. Drag the bot's role above the **{target_role_name}** role\n"
                            f"3. Save the changes"
                        ),
                        inline=False
                    )
                    
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            else:
                # Check against all user roles (excluding @everyone and managed roles)
                user_roles = [role for role in interaction.guild.roles 
                             if role.name != "@everyone" and not role.managed and role != bot_role]
                
                if user_roles:
                    highest_user_role = max(user_roles, key=lambda r: r.position)
                    if bot_role.position <= highest_user_role.position:
                        embed = discord.Embed(
                            title="⚠️ Bot Role Position Warning",
                            description=f"The bot's role should be above **{highest_user_role.name}** for best results.",
                            color=discord.Color.orange()
                        )
                        
                        embed.add_field(
                            name="🔧 Recommended Fix",
                            value=(
                                f"1. Go to Server Settings > Roles\n"
                                f"2. Drag the bot's role above **{highest_user_role.name}**\n"
                                f"3. This ensures the bot can manage all user roles properly"
                            ),
                            inline=False
                        )
                        
                        embed.add_field(
                            name="⚠️ Current Status",
                            value="The command will continue, but some operations may fail.",
                            inline=False
                        )
                        
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        # Don't return here - just warn the user
            
            return await func(self, interaction, *args, **kwargs)
        
        return wrapper
    return decorator


def safe_default_permissions():
    """Decorator that applies safe default permission checks to commands."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            # Defer response to avoid timeout
            await interaction.response.defer(ephemeral=True)
            
            # Basic safety checks
            if not interaction.guild:
                await interaction.followup.send(
                    "❌ This command can only be used in a server.",
                    ephemeral=True
                )
                return
            
            # Check if bot has basic permissions
            required_perms = ["send_messages", "embed_links"]
            missing_bot_perms = [
                perm for perm in required_perms 
                if not getattr(interaction.guild.me.guild_permissions, perm, False)
            ]
            
            if missing_bot_perms:
                perm_names = [perm.replace("_", " ").title() for perm in missing_bot_perms]
                embed = discord.Embed(
                    title="❌ Bot Missing Basic Permissions",
                    description=f"The bot needs these permissions: {', '.join(perm_names)}",
                    color=discord.Color.red()
                )
                
                embed.add_field(
                    name="🔧 How to Fix",
                    value="Please re-invite the bot with the required permissions or ask a server admin to fix the bot's role permissions.",
                    inline=False
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            return await func(self, interaction, *args, **kwargs)
        
        return wrapper
    return decorator


# Permission check decorators for common use cases
def admin_command():
    """Decorator for admin-level commands requiring Manage Server."""
    return require_any_permission("manage_guild", "administrator")


def moderator_command():
    """Decorator for moderator commands requiring Ban or Kick."""
    return require_any_permission("ban_members", "kick_members", "manage_messages")


def staff_command():
    """Decorator for staff commands requiring Manage Messages."""
    return require_any_permission("manage_messages", "manage_guild", "administrator")


def user_command():
    """Decorator for user-facing commands with safe defaults."""
    return safe_default_permissions()


# Bot permission decorators for common operations
def requires_manage_roles():
    """Decorator for commands that need to manage roles."""
    return require_bot_permission("manage_roles")


def requires_manage_channels():
    """Decorator for commands that need to manage channels."""
    return require_bot_permission("manage_channels")


def requires_ban_kick():
    """Decorator for commands that need to ban or kick members."""
    return require_any_permission("ban_members", "kick_members")


# Combined decorators for common patterns
def admin_role_management():
    """Decorator for admin-level role management commands."""
    def decorator(func: Callable) -> Callable:
        return admin_command()(requires_manage_roles()(require_bot_role_above()(func)))
    return decorator


def admin_channel_management():
    """Decorator for admin-level channel management commands."""
    def decorator(func: Callable) -> Callable:
        return admin_command()(requires_manage_channels()(func))
    return decorator


def moderator_user_management():
    """Decorator for moderator-level user management commands."""
    def decorator(func: Callable) -> Callable:
        return moderator_command()(requires_ban_kick()(func))
    return decorator
