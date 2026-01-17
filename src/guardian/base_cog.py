from __future__ import annotations

import logging
from typing import Optional, Any

import discord
from discord.ext import commands

from .utils import safe_embed, safe_response, safe_followup
from .constants import DEFAULT_TIMEOUT_SECONDS, COLORS

log = logging.getLogger("guardian.base_cog")


class BaseCog(commands.Cog):
    """Base class for all cogs with common functionality."""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.log = logging.getLogger(f"guardian.cog.{self.__class__.__name__.lower()}")
    
    async def cog_load(self) -> None:
        """Called when the cog is loaded."""
        self.log.info(f"Loaded {self.__class__.__name__}")
    
    async def cog_unload(self) -> None:
        """Called when the cog is unloaded."""
        self.log.info(f"Unloaded {self.__class__.__name__}")
    
    def error_embed(self, message: str) -> discord.Embed:
        """Create a standardized error embed."""
        return safe_embed("Error", message, COLORS["error"])
    
    def success_embed(self, message: str) -> discord.Embed:
        """Create a standardized success embed."""
        return safe_embed("Success", message, COLORS["success"])
    
    def info_embed(self, message: str) -> discord.Embed:
        """Create a standardized info embed."""
        return safe_embed("Information", message, COLORS["info"])
    
    def warning_embed(self, message: str) -> discord.Embed:
        """Create a standardized warning embed."""
        return safe_embed("Warning", message, COLORS["warning"])
    
    async def safe_response(
        self, 
        interaction: discord.Interaction,
        content: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        ephemeral: bool = False,
        **kwargs: Any,
    ) -> bool:
        """Safely respond to an interaction."""
        return await safe_response(interaction, content, embed, ephemeral, **kwargs)
    
    async def safe_followup(
        self,
        interaction: discord.Interaction,
        content: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        ephemeral: bool = False,
        **kwargs: Any,
    ) -> Optional[discord.Message]:
        """Safely follow up an interaction."""
        return await safe_followup(interaction, content, embed, ephemeral, **kwargs)
    
    def check_permissions(self, interaction: discord.Interaction, **permissions: bool) -> bool:
        """Check if the user has the required permissions."""
        if not interaction.app_permissions:
            return False
        
        for perm, required in permissions.items():
            if required and not getattr(interaction.app_permissions, perm, False):
                return False
        return True
    
    def require_admin(self, interaction: discord.Interaction) -> bool:
        """Check if the user is an administrator."""
        return self.check_permissions(interaction, administrator=True)
    
    def require_manage_guild(self, interaction: discord.Interaction) -> bool:
        """Check if the user can manage the guild."""
        return self.check_permissions(interaction, manage_guild=True)
    
    def require_manage_channels(self, interaction: discord.Interaction) -> bool:
        """Check if the user can manage channels."""
        return self.check_permissions(interaction, manage_channels=True)
    
    def require_manage_roles(self, interaction: discord.Interaction) -> bool:
        """Check if the user can manage roles."""
        return self.check_permissions(interaction, manage_roles=True)


class AdminCog(BaseCog):
    """Base class for admin-only cogs."""
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the user has admin permissions."""
        if not self.require_admin(interaction):
            await self.safe_response(
                interaction, 
                embed=self.error_embed("You need administrator permissions to use this command."),
                ephemeral=True
            )
            return False
        return True


class ModeratorCog(BaseCog):
    """Base class for moderator cogs."""
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the user has moderator permissions."""
        if not (self.require_admin(interaction) or self.require_manage_guild(interaction)):
            await self.safe_response(
                interaction,
                embed=self.error_embed("You need moderator permissions to use this command."),
                ephemeral=True
            )
            return False
        return True
