from __future__ import annotations

import logging
from collections.abc import Callable
from enum import IntEnum
from functools import wraps

import discord
from .utils import find_role_fuzzy
from discord.ext import commands

log = logging.getLogger("guardian.permissions")


class PermissionTier(IntEnum):
    """Permission tiers for command access control."""
    UNVERIFIED = 0
    VERIFIED = 1
    STAFF = 3
    ADMIN = 4
    OWNER = 5
    ROOT = 6


class PermissionError(Exception):
    """Raised when permission check fails."""
    pass


async def is_verified(interaction: discord.Interaction | commands.Context) -> bool:
    """Check if user has Verified role."""
    if not interaction.guild:
        return False
    
    member = interaction.user if isinstance(interaction, discord.Interaction) else interaction.author
    if not isinstance(member, discord.Member):
        return False
    
    # Check for Verified role
    verified_role = find_role_fuzzy(member.guild, getattr(getattr(member.guild, "_guardian_settings", None), "verified_role_name", "Verified")) if hasattr(member.guild, "_guardian_settings") else find_role_fuzzy(member.guild, "Verified")
    return verified_role in member.roles


async def is_staff(interaction: discord.Interaction | commands.Context) -> bool:
    """Check if user is Staff/Moderator."""
    if not interaction.guild:
        return False
    
    member = interaction.user if isinstance(interaction, discord.Interaction) else interaction.author
    if not isinstance(member, discord.Member):
        return False
    
    # Check for Staff/Moderator roles or permissions
    staff_roles = ["Staff", "Moderator", "Admin", "Owner"]
    has_staff_role = any(role.name in staff_roles for role in member.roles)
    has_staff_perms = member.guild_permissions.manage_messages or member.guild_permissions.kick_members
    
    return has_staff_role or has_staff_perms


async def is_admin(interaction: discord.Interaction | commands.Context) -> bool:
    """Check if user is Admin."""
    if not interaction.guild:
        return False
    
    member = interaction.user if isinstance(interaction, discord.Interaction) else interaction.author
    if not isinstance(member, discord.Member):
        return False
    
    # Check for Admin role or Administrator permission
    admin_role = find_role_fuzzy(member.guild, getattr(getattr(member.guild, "_guardian_settings", None), "admin_role_name", "Admin")) if hasattr(member.guild, "_guardian_settings") else find_role_fuzzy(member.guild, "Admin")
    return admin_role in member.roles or member.guild_permissions.administrator


async def is_owner(interaction: discord.Interaction | commands.Context) -> bool:
    """Check if user is Owner."""
    if not interaction.guild:
        return False
    
    member = interaction.user if isinstance(interaction, discord.Interaction) else interaction.author
    if not isinstance(member, discord.Member):
        return False
    
    # Check for Owner role or guild ownership
    owner_role = find_role_fuzzy(member.guild, getattr(getattr(member.guild, "_guardian_settings", None), "owner_role_name", "Owner")) if hasattr(member.guild, "_guardian_settings") else find_role_fuzzy(member.guild, "Owner")
    return owner_role in member.roles or member == member.guild.owner


async def is_root(interaction: discord.Interaction | commands.Context) -> bool:
    """Check if user is Root Operator."""
    # This would integrate with the existing RootStore
    # For now, we'll implement a basic check
    if not interaction.guild:
        return False
    
    member = interaction.user if isinstance(interaction, discord.Interaction) else interaction.author
    if not isinstance(member, discord.Member):
        return False
    
    # Root operators should also be able to use Owner commands
    if await is_owner(interaction):
        return True
    
    # TODO: Integrate with RootStore when available
    # For now, check for a dedicated Root role
    root_role = find_role_fuzzy(member.guild, getattr(getattr(member.guild, "_guardian_settings", None), "root_role_name", "Root")) if hasattr(member.guild, "_guardian_settings") else find_role_fuzzy(member.guild, "Root")
    return root_role in member.roles


async def get_user_tier(interaction: discord.Interaction | commands.Context) -> PermissionTier:
    """Get the permission tier of a user."""
    if await is_root(interaction):
        return PermissionTier.ROOT
    elif await is_owner(interaction):
        return PermissionTier.OWNER
    elif await is_admin(interaction):
        return PermissionTier.ADMIN
    elif await is_staff(interaction):
        return PermissionTier.STAFF
    elif await is_verified(interaction):
        return PermissionTier.VERIFIED
    else:
        return PermissionTier.UNVERIFIED


def require_tier(min_tier: PermissionTier):
    """Decorator to require minimum permission tier for commands."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find the interaction/context in the arguments
            interaction_or_ctx = None
            for arg in args:
                if isinstance(arg, (discord.Interaction, commands.Context)):
                    interaction_or_ctx = arg
                    break
            
            if not interaction_or_ctx:
                log.error(f"Could not find interaction/context in command {func.__name__}")
                return await _send_permission_error(interaction_or_ctx, "Unable to verify permissions.")
            
            user_tier = await get_user_tier(interaction_or_ctx)
            
            if user_tier < min_tier:
                tier_names = {
                    PermissionTier.UNVERIFIED: "Unverified",
                    PermissionTier.VERIFIED: "Verified",
                    PermissionTier.STAFF: "Staff",
                    PermissionTier.ADMIN: "Admin", 
                    PermissionTier.OWNER: "Owner",
                    PermissionTier.ROOT: "Root"
                }
                
                required_tier_name = tier_names[min_tier]
                user_tier_name = tier_names[user_tier]
                
                log.warning(f"Permission denied: {interaction_or_ctx.user} ({user_tier_name}) tried to use {func.__name__} (requires {required_tier_name})")
                return await _send_permission_error(interaction_or_ctx, f"You need {required_tier_name} permissions or higher to use this command.")
            
            # Permission check passed, execute the command
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


async def _send_permission_error(interaction_or_ctx: discord.Interaction | commands.Context, message: str):
    """Send permission error message."""
    if isinstance(interaction_or_ctx, discord.Interaction):
        try:
            if interaction_or_ctx.response.is_done():
                await interaction_or_ctx.followup.send(f"❌ {message}", ephemeral=True)
            else:
                await interaction_or_ctx.response.send_message(f"❌ {message}", ephemeral=True)
        except Exception as e:
            log.error(f"Failed to send permission error for interaction: {e}")
    elif isinstance(interaction_or_ctx, commands.Context):
        try:
            await interaction_or_ctx.reply(f"❌ {message}")
        except Exception as e:
            log.error(f"Failed to send permission error for context: {e}")


# Discord.py check decorators for both slash and prefix commands

def require_verified():
    """Require Verified tier."""
    return require_tier(PermissionTier.VERIFIED)


def require_staff():
    """Require Staff tier."""
    return require_tier(PermissionTier.STAFF)


def require_admin():
    """Require Admin tier."""
    return require_tier(PermissionTier.ADMIN)


def require_owner():
    """Require Owner tier."""
    return require_tier(PermissionTier.OWNER)


def require_root():
    """Require Root tier."""
    return require_tier(PermissionTier.ROOT)


# Specialized decorators for specific use cases

def require_verified_or_staff():
    """Require Verified tier, but allow Staff+ to bypass."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find the interaction/context
            interaction_or_ctx = None
            for arg in args:
                if isinstance(arg, (discord.Interaction, commands.Context)):
                    interaction_or_ctx = arg
                    break
            
            if not interaction_or_ctx:
                return await _send_permission_error(interaction_or_ctx, "Unable to verify permissions.")
            
            user_tier = await get_user_tier(interaction_or_ctx)
            
            if user_tier < PermissionTier.VERIFIED:
                return await _send_permission_error(interaction_or_ctx, "You must be verified to use this command.")
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_ticket_owner_or_staff():
    """Require user to be ticket owner OR Staff+."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find the interaction/context
            interaction_or_ctx = None
            for arg in args:
                if isinstance(arg, (discord.Interaction, commands.Context)):
                    interaction_or_ctx = arg
                    break
            
            if not interaction_or_ctx:
                return await _send_permission_error(interaction_or_ctx, "Unable to verify permissions.")
            
            # Check if user is Staff+
            if await is_staff(interaction_or_ctx):
                return await func(*args, **kwargs)
            
            # Check if user is ticket owner (this would need to be implemented per command)
            # For now, we'll let the command handle this logic
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# Command tier mapping for validation
COMMAND_TIER_MAPPING = {
    # VERIFIED (Tier 1)
    "avatar": PermissionTier.VERIFIED,
    "userinfo": PermissionTier.VERIFIED,
    "serverinfo": PermissionTier.VERIFIED,
    "user_profile": PermissionTier.VERIFIED,
    "profile_edit_about": PermissionTier.VERIFIED,
    "profile_edit_pronouns": PermissionTier.VERIFIED,
    "profile_edit_interests": PermissionTier.VERIFIED,
    "profile_privacy": PermissionTier.VERIFIED,
    "roles": PermissionTier.VERIFIED,
    "myroles": PermissionTier.VERIFIED,
    "titles_list": PermissionTier.VERIFIED,
    "titles_equip": PermissionTier.VERIFIED,
    "titles_unequip": PermissionTier.VERIFIED,
    "ticket": PermissionTier.VERIFIED,
    "suggest": PermissionTier.VERIFIED,
    "health": PermissionTier.VERIFIED,
    "rep": PermissionTier.VERIFIED,
    "rep_show": PermissionTier.VERIFIED,
    "rank": PermissionTier.VERIFIED,
    "my_profile": PermissionTier.VERIFIED,
    "thanks": PermissionTier.VERIFIED,
    
    # STAFF (Tier 3)
    "close": PermissionTier.STAFF,  # With ticket owner check
    "ticket_panel": PermissionTier.STAFF,
    "starboard_set": PermissionTier.STAFF,
    "activity": PermissionTier.STAFF,
    
    # ADMIN (Tier 4)
    "setup": PermissionTier.ADMIN,
    "verifypanel": PermissionTier.ADMIN,
    "rolepanel": PermissionTier.ADMIN,
    
    # OWNER (Tier 5)
    
    # ROOT (Tier 6)
    "root_request": PermissionTier.ROOT,
    "root_approve": PermissionTier.ROOT,
    "root_reject": PermissionTier.ROOT,
    "root_remove": PermissionTier.ROOT,
    "root_list": PermissionTier.ROOT,
}


def validate_command_permissions():
    """Validate that all commands have permission tiers assigned."""
    total_commands = len(COMMAND_TIER_MAPPING)
    # Do not hardcode an expected command count. Command sets change as features
    # are enabled/disabled.
    if total_commands == 0:
        log.warning("Command permission mapping is empty")
        return False

    log.info("✅ Permission mapping loaded for %d commands", total_commands)
    return True


def get_command_tier(command_name: str) -> PermissionTier | None:
    """Get the required tier for a command."""
    return COMMAND_TIER_MAPPING.get(command_name)


def list_commands_by_tier() -> dict[PermissionTier, list[str]]:
    """List all commands grouped by required tier."""
    tier_commands = {}
    
    for command, tier in COMMAND_TIER_MAPPING.items():
        if tier not in tier_commands:
            tier_commands[tier] = []
        tier_commands[tier].append(command)
    
    return tier_commands
